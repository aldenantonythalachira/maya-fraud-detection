# Local demo threat model and privacy

## Trust boundaries

This server listens on loopback. It demonstrates state integrity under accidental
retries, concurrent local clients, stale views and clients submitting invalid
commands. It is not a bank deployment or a defense against a malicious device
administrator. Anyone able to read its terminal, source process memory or database
has privileged local access. Do not expose it through a tunnel or bind it publicly.

| Actor | Permitted access | Boundary |
|---|---|---|
| Payer session | Its worlds, intents, reviews, settlement, contact consent, recipient sharing and deletion | HttpOnly same-site cookie; session/world ownership checked by backend |
| Recipient observer | One synthetic recipient's identity, balance and matching incoming transfers | Random scoped token; stored hashed, <=1h lifetime, payer revocation |
| Trusted contact | Minimal consented hold alerts; durable acknowledgment | Independent controller-issued token, expiry/revocation; no approval or debit |
| Analyst | Held >INR100,000 cases; approve exact review, cancel, file mock case | Independent controller-issued token, recorded actor; no timer bypass |
| Demo controller | List local worlds, issue/revoke roles, mutate virtual evidence/time, fork counterfactuals | Startup key printed only to terminal; excluded from payer UI/API payloads |

Tokens are bearer capabilities, not verified human identities. Do not share the
controller terminal or key during a public demo. Controller key rotates on server
restart; independent grants expire according to real wall time, not virtual time.
Role links carry a token in a fragment, consumed and removed from address bar;
role tokens are then held in memory. Recipient tokens persist in that tab's
sessionStorage for refresh. No key/token is intentionally written to application
logs. Access events use a short hashed actor identifier, never the raw token.

Same-origin middleware, trusted host checking, strict typed inputs/extra-field
rejection, payload limits, a local mutation rate budget, CSP and no-cache/referrer
headers reduce browser misuse. HTTPS cookies use Secure; loopback HTTP does not.
API docs are off unless `--demo-docs` is explicitly set. The rate budget is per
process and does not claim to resist distributed attackers or unlimited reads.

## Consent and retention

Only synthetic data is accepted in this demo. No PIN fields, phone sensors, real
messages, contacts, location, voice, screen contents or typing biometrics exist.
Message sharing is explicit and text is discarded before persistence if consent
is absent. Contact sharing has a separate opt-in; revocation disables access and
future alerts. Revocation does not rewrite old immutable reviews. Old consented
synthetic message snapshots persist until the payer deletes the world.

World deletion intentionally purges its reviews, ledger, events, grants, transfers
and intents in one transaction. It is the explicit exception to review retention
triggers. It is logical deletion, not cryptographic erasure of SQLite free pages
or backups. Browser world/payment pointers can outlive deleted server data and
recover by creating a new world. There is no automatic retention scheduler.

## Integrity and failures

Review and bundle SHA256 digests detect changed contents; a manifest binds model
and calibration files. These are not signatures, HSM protection or independent
proof against database administrators. Update triggers reject ordinary changes
to saved reviews, ledger, transfers and events. A privileged admin can remove them.

The system blocks new authorization when model artifacts are unavailable or a
model evaluation fails. A successful fresh review can restore a transiently failed
runtime scorer. Missing artifacts require bootstrap and restart. No stale score,
fake clean provider verdict or hidden fallback release is substituted.

Future bank work needs proper identity/role management, authenticated key
provisioning, encryption/key rotation, signed artifacts, independent audit storage,
dual-person evidence access, migrations, formal data retention and an approved
bank-rules fallback. Those properties are not claimed by this local system.
