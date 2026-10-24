"""Reproducible synthetic worlds. Presets change causes, never model outputs."""
import random
from datetime import datetime, timezone

GENERATOR_VERSION = "world-v1"
DAY = 86400
EPOCH = int(datetime(2026, 10, 22, 12, tzinfo=timezone.utc).timestamp())


def generate_world(seed, preset="everyday"):
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Seed must be an integer between 0 and 4294967295")
    if preset not in ("everyday", "investment", "refund", "probes"):
        raise ValueError("Unknown world preset")
    rng = random.Random(seed)
    suffix = f"{rng.randrange(1000, 10000)}"
    names = [("payer", "You", False), ("family", "Amma", False),
             ("rent", "Ananya · Rent", False), ("shop", "Corner Store", True),
             ("trader", "R K Traders", False), ("collector", "City Collections", False)]
    accounts = [dict(id=i, vpa=f"{key}.{suffix}@demo", name=name,
                     business=business, opening_paise=50_000_000 if i == 0 else rng.randint(100_000, 3_000_000))
                for i, (key, name, business) in enumerate(names)]
    for i in range(6, 80):
        accounts.append(dict(id=i, vpa=f"person{i}.{suffix}@demo", name=f"Demo person {i}",
                             business=False, opening_paise=rng.randint(300_000, 6_000_000)))
    events = []

    def payment(sender, receiver, amount, at):
        events.append(dict(id=f"history-{len(events)}", kind="payment", sender=sender,
                           receiver=receiver, amount_paise=amount, event_at=at, available_at=at,
                           provenance="generated settled payment"))

    # Familiar payees have actual, variable prior history on both endpoints.
    for day in range(27, 0, -1):
        payee = rng.choice([1, 2, 3])
        payment(0, payee, rng.randint(500, 8000) * 100, EPOCH - day * DAY - rng.randint(60, 3000))
    payment(0, 1, rng.randint(3000, 6000) * 100, EPOCH - 2 * DAY)
    payment(0, 2, 2_000_000, EPOCH - 25 * DAY)
    if preset in ("investment", "probes"):
        # A crowded receiving account, small initial transfers, and a profit hook.
        for sender in range(6, rng.randint(68, 80)):
            payment(sender, 4, rng.randint(50, 500) * 100, EPOCH - rng.randint(2 * DAY, 6 * DAY))
        payment(4, 0, rng.randint(900, 1500) * 100, EPOCH - 4 * DAY)
        payment(0, 4, rng.randint(2000, 5000) * 100, EPOCH - 2 * DAY)
        payment(5, 4, rng.randint(500, 2000) * 100, EPOCH - 3 * DAY)
        events.append(dict(id="report-collector", kind="report", account=5,
                           event_at=EPOCH - 3 * DAY, available_at=EPOCH - 2 * DAY,
                           provenance="synthetic confirmed report; not NCRP"))
    if preset == "probes":
        for i, paise in enumerate((100, 200, 500)):
            payment(0, 4, paise, EPOCH - 300 + i * 30)
    if preset == "refund":
        payment(6, 4, rng.randint(100, 400) * 100, EPOCH - 2 * DAY)
    events.sort(key=lambda e: (e["event_at"], e["id"]))
    return dict(seed=seed, preset=preset, generator_version=GENERATOR_VERSION,
                now=EPOCH, revision=1, accounts=accounts, events=events,
                default_recipient=1 if preset == "everyday" else 4,
                default_amount_paise=rng.randint(1500, 5000) * 100 if preset == "everyday" else rng.randint(15000, 35000) * 100,
                default_message="Approve to receive your refund" if preset == "refund" else "")
