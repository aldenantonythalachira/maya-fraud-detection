"""Persistent, local-only dummy wallet. No real bank/UPI connection.

SQLite transactions, not Python locks, establish settlement atomicity. The lock
protects this connection; separate connections serialize through BEGIN IMMEDIATE.
"""
import hashlib
import json
import math
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy

from claims import compare_claim, extract_claim
from online_features import FEATURE_VERSION, numeric, snapshot
from payment_review import canonical, digest
from policy import DEFAULT_THRESHOLDS, decide, hard_signals
from risk_common import FEATURE_COLUMNS, english_reason
from simulation import generate_world

POLICY_VERSION = "wallet-policy-v1"


def apply_policy(payment, features, model):
    claim = extract_claim(payment["text"], payment["consent"])
    comparison = compare_claim(claim, "outgoing")
    soft = {"chat_stage": "payment_demand"} if comparison in ("direction_contradiction", "unverified_future_benefit") else {}
    hard = hard_signals(numeric(features["values"]), DEFAULT_THRESHOLDS)
    groups = dict(history=any(hard[k] for k in ("n_t", "e_t", "z_t", "pi_t")), recipient=hard["d_R"], context=bool(soft))
    reasons = []
    if groups["history"]:
        reasons.append("This payment differs from the available payment history.")
    if groups["recipient"]:
        reasons.append("A prior-day payment path connects a reported account to this recipient or payer.")
    if comparison == "direction_contradiction":
        reasons.append("The message says you will receive money. This payment sends money.")
    elif comparison == "unverified_future_benefit":
        reasons.append("This payment cannot verify the promised investment withdrawal.")
    decision = decide(model["uncertainty"], numeric(features["values"]), soft, reasons, payment["amount_paise"] / 100)
    if comparison == "direction_contradiction" and decision["action"] == "release":
        decision.update(action="nudge", reasons=[reasons[-1]])
    if decision["action"] == "hold" and not (groups["history"] and groups["recipient"] or
            (groups["history"] or groups["recipient"]) and groups["context"]):
        raise ValueError("Independent policy verifier rejected hold")
    return decision, claim, comparison, groups


class LiveModel:
    def __init__(self, model_path, calibration_path):
        from payment_review import ModelAdapter
        self.adapter = ModelAdapter(model_path, calibration_path)
        self.version = self.adapter.version
        self.calibration_version = self.adapter.calibration_version

    def score(self, values):
        import pandas as pd
        import xgboost as xgb
        result = self.adapter.score(values)
        row = pd.DataFrame([values], columns=FEATURE_COLUMNS).astype("float32")
        contrib = self.adapter.model.get_booster().predict(
            xgb.DMatrix(row, feature_names=FEATURE_COLUMNS), pred_contribs=True)[0]
        result["contributions"] = [dict(feature=k, value=float(v), label=english_reason(k))
                                   for k, v in zip(FEATURE_COLUMNS, contrib[:-1])]
        result["base_margin"] = float(contrib[-1])
        return result


class Simulator:
    def __init__(self, database, model):
        self.model = model
        self.lock = threading.RLock()
        self.db = sqlite3.connect(database, timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sim_world(id TEXT PRIMARY KEY, owner TEXT NOT NULL, observer TEXT UNIQUE NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sim_intent(id TEXT PRIMARY KEY, world TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sim_review(id TEXT PRIMARY KEY, world TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sim_transfer(id TEXT PRIMARY KEY, payment TEXT UNIQUE NOT NULL, world TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sim_ledger(id INTEGER PRIMARY KEY, world TEXT NOT NULL, transfer TEXT NOT NULL, account INTEGER NOT NULL, delta INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS sim_event(sequence INTEGER PRIMARY KEY AUTOINCREMENT, world TEXT NOT NULL, body TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS sim_event_world ON sim_event(world, sequence);
            CREATE INDEX IF NOT EXISTS sim_ledger_world ON sim_ledger(world, account);
            CREATE TRIGGER IF NOT EXISTS sim_immutable_review BEFORE UPDATE ON sim_review BEGIN SELECT RAISE(ABORT,'immutable review'); END;
            CREATE TRIGGER IF NOT EXISTS sim_retain_review BEFORE DELETE ON sim_review BEGIN SELECT RAISE(ABORT,'immutable review'); END;
        """)
        self.db.commit()

    @contextmanager
    def transaction(self):
        with self.lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                yield
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def _world(self, wid, owner):
        row = self.db.execute("SELECT * FROM sim_world WHERE id=?", (wid,)).fetchone()
        if row is None or not secrets.compare_digest(row["owner"], owner):
            raise ValueError("World not found for this session")
        return json.loads(row["body"])

    def _intent(self, pid, wid):
        row = self.db.execute("SELECT body FROM sim_intent WHERE id=? AND world=?", (pid, wid)).fetchone()
        if row is None:
            raise ValueError("Payment not found")
        return json.loads(row[0])

    def _save_world(self, world):
        self.db.execute("UPDATE sim_world SET body=? WHERE id=?", (canonical(world), world["id"]))

    def _save_intent(self, payment):
        self.db.execute("UPDATE sim_intent SET body=? WHERE id=?", (canonical(payment), payment["id"]))

    def _event(self, wid, stage, payment=None, **details):
        self.db.execute("INSERT INTO sim_event(world,body) VALUES(?,?)",
                        (wid, canonical(dict(stage=stage, payment_id=payment, recorded_at=time.time(), **details))))

    def emit(self, wid, stage, payment=None, **details):
        with self.transaction():
            self._event(wid, stage, payment, **details)

    def create_world(self, owner, seed, preset):
        world = generate_world(seed, preset)
        world["id"] = uuid.uuid4().hex
        observer = secrets.token_urlsafe(32)
        with self.transaction():
            self.db.execute("INSERT INTO sim_world VALUES(?,?,?,?)", (world["id"], owner, observer, canonical(world)))
            for account in world["accounts"]:
                self.db.execute("INSERT INTO sim_ledger(world,transfer,account,delta) VALUES(?,?,?,?)",
                                (world["id"], "genesis", account["id"], account["opening_paise"]))
            for event in world["events"]:
                if event["kind"] == "payment":
                    for account, sign in ((event["sender"], -1), (event["receiver"], 1)):
                        self.db.execute("INSERT INTO sim_ledger(world,transfer,account,delta) VALUES(?,?,?,?)",
                                        (world["id"], event["id"], account, sign * event["amount_paise"]))
            self._event(world["id"], "world_created", seed=seed, preset=preset, generator=world["generator_version"])
        return self.read_world(world["id"], owner)

    def read_world(self, wid, owner):
        with self.lock:
            world = self._world(wid, owner)
            accounts = deepcopy(world["accounts"])
            for account in accounts:
                account["balance_paise"] = self.balance(wid, account["id"])
            transfers = [json.loads(r[0]) for r in self.db.execute("SELECT body FROM sim_transfer WHERE world=? ORDER BY rowid DESC", (wid,))]
            intents = [json.loads(r[0]) for r in self.db.execute("SELECT body FROM sim_intent WHERE world=? ORDER BY rowid DESC", (wid,))]
            observer = self.db.execute("SELECT observer FROM sim_world WHERE id=?", (wid,)).fetchone()[0]
            return dict(**{k: v for k, v in world.items() if k not in ("accounts", "events")}, accounts=accounts,
                        transfers=transfers, intents=intents, observer=observer,
                        event_count=len(world["events"]), model_version=self.model.version,
                        calibration_version=self.model.calibration_version, feature_version=FEATURE_VERSION)

    def balance(self, wid, account):
        return self.db.execute("SELECT COALESCE(SUM(delta),0) FROM sim_ledger WHERE world=? AND account=?", (wid, account)).fetchone()[0]

    def observe(self, token):
        with self.lock:
            row = self.db.execute("SELECT id,owner FROM sim_world WHERE observer=?", (token,)).fetchone()
            if row is None:
                raise ValueError("Observer link not found")
            result = self.read_world(row[0], row[1])
            return {k: result[k] for k in ("id", "seed", "now", "accounts", "transfers")}

    @staticmethod
    def validate(world, recipient, amount, text, consent):
        if type(recipient) is not int or recipient == 0 or recipient not in {a["id"] for a in world["accounts"]}:
            raise ValueError("Choose a synthetic recipient other than the payer")
        if type(amount) is not int or not 0 < amount <= 100_000_000:
            raise ValueError("Amount must be positive integer paise, at most INR 1,000,000")
        if not isinstance(text, str) or len(text) > 2000 or type(consent) is not bool:
            raise ValueError("Invalid message or consent")

    def intent(self, wid, owner, recipient, amount, text="", consent=False, pid=None):
        with self.transaction():
            world = self._world(wid, owner)
            self.validate(world, recipient, amount, text, consent)
            if pid:
                payment = self._intent(pid, wid)
                if payment["state"] != "pending":
                    raise ValueError("Payment is terminal")
                payment["revision"] += 1
            else:
                payment = dict(id=uuid.uuid4().hex, world=wid, revision=1, state="pending", direction="outgoing")
            # Unconsented text never enters storage or trace.
            payment.update(recipient=recipient, amount_paise=amount, text=text if consent else "", consent=consent)
            if pid:
                self._save_intent(payment)
            else:
                self.db.execute("INSERT INTO sim_intent VALUES(?,?,?)", (payment["id"], wid, canonical(payment)))
            self._event(wid, "intent_validated", payment["id"], revision=payment["revision"], amount_paise=amount)
            return payment

    def review(self, wid, owner, pid, parent=None):
        started = time.perf_counter()
        with self.lock:
            world = self._world(wid, owner)
            payment = self._intent(pid, wid)
            if payment["state"] != "pending":
                raise ValueError("Payment is terminal")
            if parent:
                self.replay(wid, owner, parent)
        self.emit(wid, "history_loaded", pid, world_revision=world["revision"], evaluation_time=world["now"])
        features = snapshot(world, 0, payment["recipient"], payment["amount_paise"], world["now"])
        self.emit(wid, "features_computed", pid, feature_version=FEATURE_VERSION, evidence_count=len(features["evidence"]))
        model = self.model.score(numeric(features["values"]))
        self.emit(wid, "model_scored", pid, model_version=self.model.version)
        self.emit(wid, "uncertainty_computed", pid, calibration_version=self.model.calibration_version)
        decision, claim, comparison, groups = apply_policy(payment, features, model)
        self.emit(wid, "policy_evaluated", pid, action=decision["action"], groups=groups)
        record = dict(id=uuid.uuid4().hex, payment=deepcopy(payment), world_revision=world["revision"],
                      evaluated_at=world["now"], expires_at=world["now"] + 300,
                      feature_snapshot=features, model=model, decision=decision, groups=groups,
                      claim=claim, comparison=comparison, parent=parent,
                      versions=dict(model=self.model.version, calibration=self.model.calibration_version,
                                    policy=POLICY_VERSION, features=FEATURE_VERSION),
                      latency_ms=(time.perf_counter() - started) * 1000)
        record["digest"] = digest(record)
        with self.transaction():
            current = self._world(wid, owner)
            if current["revision"] != world["revision"] or self._intent(pid, wid) != payment:
                raise ValueError("Inputs changed during review; review again")
            self.db.execute("INSERT INTO sim_review VALUES(?,?,?)", (record["id"], wid, canonical(record)))
            if decision["action"] == "hold":
                if payment.get("hold_revision") != payment["revision"]:
                    payment.update(hold_until=world["now"] + 3600, hold_revision=payment["revision"],
                                   analyst_required=decision["requires_analyst"], analyst_approved=False)
                    # One durable contact alert per world/payer/simulated day.
                    day = int(world["now"]) // 86400
                    if world.get("last_alert_day") != day:
                        self._event(wid, "trusted_contact_alert", pid, message="A simulated payment is held for review.", virtual_day=day)
                        world["last_alert_day"] = day
                        self._save_world(world)
                    self._save_intent(payment)
            self._event(wid, "review_saved", pid, review_id=record["id"], latency_ms=record["latency_ms"])
        return record

    def replay(self, wid, owner, rid, recompute=False):
        with self.lock:
            self._world(wid, owner)
            row = self.db.execute("SELECT body FROM sim_review WHERE id=? AND world=?", (rid, wid)).fetchone()
            if row is None:
                raise ValueError("Review not found")
            record = json.loads(row[0])
        if digest({k: v for k, v in record.items() if k != "digest"}) != record["digest"]:
            raise ValueError("Review integrity failed")
        if recompute:
            self._versions(record)
            actual = self.model.score(numeric(record["feature_snapshot"]["values"]))
            if actual != record["model"]:
                raise ValueError("Model replay differs")
            decision, claim, comparison, groups = apply_policy(record["payment"], record["feature_snapshot"], actual)
            if (decision, claim, comparison, groups) != (record["decision"], record["claim"], record["comparison"], record["groups"]):
                raise ValueError("Policy replay differs")
        return record

    def _versions(self, record):
        if record["versions"] != dict(model=self.model.version, calibration=self.model.calibration_version,
                                       policy=POLICY_VERSION, features=FEATURE_VERSION):
            raise ValueError("Model or policy version changed; review again")

    def _valid_review(self, world, payment, record):
        self._versions(record)
        keys = ("id", "world", "revision", "recipient", "amount_paise", "text", "consent", "state", "direction")
        if any(payment[k] != record["payment"][k] for k in keys):
            raise ValueError("Payment or consent changed; review again")
        if world["revision"] != record["world_revision"]:
            raise ValueError("Evidence changed; review again")
        if world["now"] >= record["expires_at"]:
            raise ValueError("Review expired; review again")

    def execute(self, wid, owner, pid, rid, confirmed, authorization):
        with self.transaction():
            world = self._world(wid, owner)
            payment = self._intent(pid, wid)
            prior = self.db.execute("SELECT body FROM sim_transfer WHERE payment=?", (pid,)).fetchone()
            if prior:
                transfer = json.loads(prior[0])
                if transfer["review_id"] != rid:
                    raise ValueError("Payment already settled with a different review")
                return transfer  # Intent ID is the durable idempotency key.
            if payment["state"] != "pending":
                raise ValueError("Payment is terminal")
            record = self.replay(wid, owner, rid)
            self._valid_review(world, payment, record)
            if payment.get("hold_revision") == payment["revision"]:
                if world["now"] < payment["hold_until"]:
                    raise ValueError("Payment held; cancel or wait for a fresh review after the timer")
                if payment["analyst_required"] and not payment["analyst_approved"]:
                    raise ValueError("Simulated analyst approval required")
                if not confirmed:
                    raise ValueError("Explicit warning confirmation required")
            if record["decision"]["action"] == "nudge" and not confirmed:
                raise ValueError("Explicit warning confirmation required")
            if authorization != "DEMO":
                raise ValueError("Demo authorization required; never enter a real PIN")
            if self.balance(wid, 0) < payment["amount_paise"]:
                raise ValueError("Insufficient dummy balance")
            transfer = dict(id=uuid.uuid4().hex, payment_id=pid, review_id=rid, recipient=payment["recipient"],
                            amount_paise=payment["amount_paise"], timestamp=world["now"], state="completed")
            self.db.execute("INSERT INTO sim_transfer VALUES(?,?,?,?)", (transfer["id"], pid, wid, canonical(transfer)))
            for account, sign in ((0, -1), (payment["recipient"], 1)):
                self.db.execute("INSERT INTO sim_ledger(world,transfer,account,delta) VALUES(?,?,?,?)",
                                (wid, transfer["id"], account, sign * payment["amount_paise"]))
            payment["state"] = "completed"
            self._save_intent(payment)
            world["events"].append(dict(id=transfer["id"], kind="payment", sender=0, receiver=payment["recipient"],
                                        amount_paise=payment["amount_paise"], event_at=world["now"],
                                        available_at=world["now"], provenance="live dummy settlement"))
            world["revision"] += 1
            world["now"] += 1  # Next intent sees the committed transfer, never its own candidate.
            self._save_world(world)
            self._event(wid, "settled", pid, transfer=transfer, debit=-payment["amount_paise"], credit=payment["amount_paise"])
            return transfer

    def cancel(self, wid, owner, pid):
        with self.transaction():
            self._world(wid, owner)
            payment = self._intent(pid, wid)
            if payment["state"] != "pending":
                raise ValueError("Payment is terminal")
            payment["state"] = "cancelled"
            self._save_intent(payment)
            self._event(wid, "cancelled", pid)
            return payment

    def control(self, wid, owner, operation, pid=None, account=None, seconds=0, review_id=None):
        with self.transaction():
            world = self._world(wid, owner)
            if operation == "advance":
                if type(seconds) is not int or not 1 <= seconds <= 7 * 86400:
                    raise ValueError("Advance must be 1 second to 7 days")
                world["now"] += seconds
                world["revision"] += 1
            elif operation == "report":
                if type(account) is not int or account not in {a["id"] for a in world["accounts"]}:
                    raise ValueError("Unknown account")
                world["events"].append(dict(id=uuid.uuid4().hex, kind="report", account=account,
                                            event_at=world["now"] - 1, available_at=world["now"] - 1,
                                            provenance="manually injected synthetic report"))
                world["revision"] += 1
            elif operation == "delay_reports":
                reports = [e for e in world["events"] if e["kind"] == "report"]
                if not reports:
                    raise ValueError("This world has no reports to delay")
                for report in reports:
                    report["available_at"] = world["now"] + 86400
                world["revision"] += 1
            elif operation == "approve":
                payment = self._intent(pid, wid)
                record = self.replay(wid, owner, review_id)
                self._valid_review(world, payment, record)
                if payment["state"] != "pending" or payment.get("hold_revision") != payment["revision"]:
                    raise ValueError("No current held revision")
                if not payment.get("analyst_required"):
                    raise ValueError("Analyst approval is not required")
                payment["analyst_approved"] = True
                self._save_intent(payment)
            else:
                raise ValueError("Unknown simulator control")
            self._save_world(world)
            self._event(wid, "simulator_" + operation, pid, virtual_time=world["now"])
        return self.read_world(wid, owner)

    def events(self, wid, owner, after=0):
        with self.lock:
            self._world(wid, owner)
            return [dict(sequence=r[0], **json.loads(r[1])) for r in self.db.execute(
                "SELECT sequence,body FROM sim_event WHERE world=? AND sequence>? ORDER BY sequence LIMIT 500", (wid, after))]

    def ledger(self, wid, owner, transfer):
        with self.lock:
            self._world(wid, owner)
            return [dict(r) for r in self.db.execute("SELECT transfer,account,delta FROM sim_ledger WHERE world=? AND transfer=?", (wid, transfer))]
