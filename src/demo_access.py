"""Scoped, expiring demo capabilities. Controller provisioning is outside payer UI.

These local bearer capabilities demonstrate role separation, not bank identity.
Contact alerts are read from committed sim_event records: this is a durable local
inbox, not external SMS delivery. Acknowledgment never authorizes a payment.
"""
import hashlib
import json
import secrets
import time

from payment_review import canonical


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Access:
    def setup_access(self):
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS sim_access (
            id TEXT PRIMARY KEY, world TEXT NOT NULL, role TEXT NOT NULL,
            account INTEGER, expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
            acknowledged INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS sim_purge(world TEXT PRIMARY KEY);
          CREATE UNIQUE INDEX IF NOT EXISTS sim_ledger_once ON sim_ledger(world,transfer,account);
          CREATE TRIGGER IF NOT EXISTS sim_fixed_ledger BEFORE UPDATE ON sim_ledger
            BEGIN SELECT RAISE(ABORT,'immutable ledger'); END;
          CREATE TRIGGER IF NOT EXISTS sim_fixed_transfer BEFORE UPDATE ON sim_transfer
            BEGIN SELECT RAISE(ABORT,'immutable transfer'); END;
          CREATE TRIGGER IF NOT EXISTS sim_fixed_event BEFORE UPDATE ON sim_event
            BEGIN SELECT RAISE(ABORT,'append-only event'); END;
          DROP TRIGGER IF EXISTS sim_retain_review;
          CREATE TRIGGER sim_retain_review BEFORE DELETE ON sim_review
            WHEN NOT EXISTS (SELECT 1 FROM sim_purge WHERE world=OLD.world)
            BEGIN SELECT RAISE(ABORT,'immutable review'); END;
        """)
        self.db.commit()

    def _mint(self, wid, role, account=None, ttl=1800):
        if role not in ('observer', 'contact', 'analyst') or not 30 <= ttl <= 3600:
            raise ValueError('Invalid access scope or lifetime')
        token = secrets.token_urlsafe(32)
        self.db.execute('INSERT INTO sim_access(id,world,role,account,expires) VALUES(?,?,?,?,?)',
                        (token_hash(token), wid, role, account, time.time() + ttl))
        self._event(wid, 'access_issued', role=role, account=account, ttl_seconds=ttl)
        return token

    def share(self, wid, owner, account, role='observer', ttl=1800):
        # Only observers can be issued by the payer. Other roles use provisioning.
        if role != 'observer':
            raise ValueError('Independent role provisioning required')
        with self.transaction():
            world = self._world(wid, owner)
            if account == 0 or account not in {a['id'] for a in world['accounts']}:
                raise ValueError('Choose a recipient')
            return dict(token=self._mint(wid, role, account, ttl), expires_in=ttl)

    def provision(self, wid, role, ttl=1800):
        # Called only after API controller authentication, never a payer route.
        if role not in ('analyst', 'contact'):
            raise ValueError('Unsupported independent role')
        with self.transaction():
            if self.db.execute('SELECT 1 FROM sim_world WHERE id=?', (wid,)).fetchone() is None:
                raise ValueError('World not found')
            return dict(token=self._mint(wid, role, ttl=ttl), expires_in=ttl, role=role)

    def _access(self, token, role=None):
        if not isinstance(token, str) or len(token) > 128:
            raise ValueError('Access unavailable')
        row = self.db.execute('SELECT * FROM sim_access WHERE id=?', (token_hash(token),)).fetchone()
        if row is None or row['revoked'] or row['expires'] <= time.time() or role and row['role'] != role:
            raise ValueError('Access expired, revoked or unavailable')
        return dict(row)

    def revoke_sharing(self, wid, owner):
        with self.transaction():
            self._world(wid, owner)
            self.db.execute("UPDATE sim_access SET revoked=1 WHERE world=? AND role='observer'", (wid,))
            self._event(wid, 'sharing_revoked')
        return dict(revoked=True)

    def role_view(self, token):
        with self.transaction():
            access = self._access(token)
            wid, role = access['world'], access['role']
            row = self.db.execute('SELECT owner FROM sim_world WHERE id=?', (wid,)).fetchone()
            if row is None:
                raise ValueError('World deleted')
            owner = row[0]
            # One access record per view request. Polling clients should be bounded.
            self._event(wid, 'evidence_accessed', role=role, actor=access['id'][:12])
            world = self.read_world(wid, owner)
            if role == 'observer':
                account = access['account']
                return dict(id=wid, role=role, seed=world['seed'], now=world['now'],
                            accounts=[{k:a[k] for k in ('id','name','vpa','balance_paise')} for a in world['accounts'] if a['id'] == account],
                            transfers=[t for t in world['transfers'] if t['recipient'] == account])
            if role == 'contact':
                # Explicit world-level consent controls contact delivery and access.
                if not world.get('contact_consent', False):
                    raise ValueError('Contact sharing is disabled by the payer')
                alerts = [dict(sequence=r[0], **json.loads(r[1])) for r in self.db.execute(
                    "SELECT sequence,body FROM sim_event WHERE world=? AND sequence>? ORDER BY sequence",
                    (wid, access['acknowledged'])) if json.loads(r[1])['stage'] == 'trusted_contact_alert']
                return dict(id=wid, role=role, alerts=alerts, now=world['now'])
            # Analysts receive case data only, no payer credentials or control token.
            cases = []
            for p in world['intents']:
                if p['state'] == 'pending' and p.get('analyst_required') and p.get('hold_revision') == p['revision']:
                    reviews = self.db.execute('SELECT body FROM sim_review WHERE world=? ORDER BY rowid DESC', (wid,))
                    latest = next((json.loads(r[0]) for r in reviews if json.loads(r[0])['payment']['id'] == p['id']), None)
                    cases.append(dict(payment=p, review=latest))
            return dict(id=wid, role=role, now=world['now'], cases=cases)

    def role_action(self, token, operation, pid=None, rid=None):
        with self.transaction():
            access = self._access(token)
            wid = access['world']
            owner = self.db.execute('SELECT owner FROM sim_world WHERE id=?', (wid,)).fetchone()[0]
            world = self._world(wid, owner)
            if operation == 'acknowledge' and access['role'] == 'contact':
                if not world.get('contact_consent', False):
                    raise ValueError('Contact sharing disabled')
                last = self.db.execute('SELECT COALESCE(MAX(sequence),0) FROM sim_event WHERE world=?', (wid,)).fetchone()[0]
                self.db.execute('UPDATE sim_access SET acknowledged=? WHERE id=?', (last, access['id']))
                self._event(wid, 'contact_acknowledged', actor=access['id'][:12])
            elif operation in ('approve', 'cancel', 'file_report') and access['role'] == 'analyst':
                payment = self._intent(pid, wid)
                record = self.replay(wid, owner, rid)
                self._valid_review(world, payment, record)
                if payment['state'] != 'pending' or payment.get('hold_revision') != payment['revision'] or not payment.get('analyst_required'):
                    raise ValueError('No current analyst case')
                if operation == 'file_report':
                    provider = world.get('providers', {}).get('NCRP', {})
                    if provider.get('status') != 'available':
                        raise ValueError('Synthetic NCRP provider unavailable; no case filed')
                    reference = 'DEMO-' + secrets.token_hex(6).upper()
                    self._event(wid, 'synthetic_ncrp_case', pid, reference=reference, review_id=rid,
                                actor=access['id'][:12], provenance='local mock; not a government report')
                    return dict(recorded=True, reference=reference)
                if operation == 'approve':
                    payment.update(analyst_approved=True, analyst_review=rid, analyst_actor=access['id'][:12])
                else:
                    payment['state'] = 'cancelled'
                self._save_intent(payment)
                self._event(wid, 'analyst_' + operation, pid, review_id=rid, actor=access['id'][:12])
            else:
                raise ValueError('Role does not permit this action')
        return dict(recorded=True)

    def contact_consent(self, wid, owner, enabled):
        if type(enabled) is not bool:
            raise ValueError('Consent must be explicit')
        with self.transaction():
            world = self._world(wid, owner)
            world['contact_consent'] = enabled
            world['revision'] += 1
            if not enabled:
                self.db.execute("UPDATE sim_access SET revoked=1 WHERE world=? AND role='contact'", (wid,))
            self._save_world(world)
            self._event(wid, 'contact_consent_changed', enabled=enabled)
        return dict(enabled=enabled)

    def delete_world(self, wid, owner):
        with self.transaction():
            self._world(wid, owner)
            self.db.execute('INSERT INTO sim_purge VALUES(?)', (wid,))
            for table in ('sim_access', 'sim_event', 'sim_review', 'sim_transfer', 'sim_intent', 'sim_ledger'):
                self.db.execute(f'DELETE FROM {table} WHERE world=?', (wid,))
            self.db.execute('DELETE FROM sim_world WHERE id=?', (wid,))
            self.db.execute('DELETE FROM sim_purge WHERE world=?', (wid,))
        return dict(deleted=True)
