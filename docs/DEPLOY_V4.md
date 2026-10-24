# Deploy MAYA V4

## What is ready to host

The customer app, read-only judge page, scoped recipient page, private intent checks and transactional sandbox service share one entrypoint: `run_demo.py`. Docker packages them behind Caddy HTTPS and PostgreSQL. Dummy money and generated histories are explicit throughout.

This is a deployable hackathon sandbox and a limited-information companion. It is not a bank-connected payment operator. Partner scoring is disabled until an authorized, source-matched model validation bundle is configured. Do not deploy the older `src/api.py` research server as the public service.

## Verified local start (Windows PowerShell)

Run from the repository directory, not your user home:

```powershell
cd C:\Users\ashrith\Downloads\Projects\raksham\maya-fraud-detection
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/bootstrap_v4.py
.\.venv\Scripts\python.exe scripts/train_wallet_bundle.py
.\.venv\Scripts\python.exe run_demo.py --port 8000
```

Open `/app/`, `/demo/` and `/recipient/`. The latter two need separate pairing codes from the customer's payment screen. Codes expire in five minutes; access expires after 30 minutes and is revocable. A paired observer cannot execute a payment.

The bootstrap preserves earlier root model artifacts under `data/checkpoints/`. Local runtime state is `data/v4/product.sqlite`; the signing/session key is `data/v4/session.key`. Preserve the key with the database. No credentials enter source control.

## What a public HTTPS release still requires

The user chose the product name **mayaupi**, but has no Docker server or cloud account connected. A public hostname, hosting account, server access and any required spending authorization remain external prerequisites. No server, paid subscription or domain has been purchased. A bare product name is not a registered domain.

Use a current supported Linux server with Docker Engine and Compose v2, public TCP 80/443, and DNS pointing the chosen hostname at the server. Review provider pricing and data location before provisioning. The deployment below creates no cloud resources by itself.

## Docker deployment on that server

1. Transfer the reviewed repository release to the server. Install Docker using its official instructions for the server OS. Keep SSH keys and cloud tokens outside the repository.
2. Set DNS for the chosen hostname. Confirm no other service owns ports 80/443.
3. Create private configuration without printing credentials:

```sh
python3 scripts/configure_deployment.py --domain your-owned-hostname.example
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
curl --fail https://your-owned-hostname.example/readyz
```

The image builds reproducible generated-data bundles. It does not contain the downloaded PaySim raw data. Caddy obtains the certificate for the configured hostname. The application runs as a non-root user with a read-only image. Only Caddy exposes public ports; PostgreSQL and the app port stay private.

The Compose network uses `172.30.4.0/24`, with Caddy at `.2`, app at `.3` and PostgreSQL at `.4`. Change these together if the server already uses that subnet. Uvicorn trusts **only Caddy's exact address**; wildcard/CIDR proxy trust is rejected by the launcher. Never publish the backend directly while trusting proxy identity. Configure host firewalls and Docker ingress together.

Configure an external uptime check for `/readyz` and alert on 5xx/429 rates, latency and database disk usage. `/livez` only establishes process liveness. Readiness means a compatible model/storage bundle, not successful real-world model validation. Forward logs without request bodies, cookies, codes or secrets.

## Scaling and database boundary

Local SQLite is single-process development storage. PostgreSQL migrations, transaction advisory locks and durable ordered events support separate service instances. Each instance currently serializes its database connection with a process lock; pool sizing and workload partitioning remain performance work, not a claimed completed optimization.

Begin with one application instance. Measure first. To add replicas, give each its own internal address and put it behind the proxy, keep the same PostgreSQL database/session secret/model bundle, and configure a shared gateway rate limit. In-process request budgets and stream slots are **per replica**, so simply adding replicas does not provide a global tenant quota. No 10,000-transactions/second or national-UPI capacity is claimed.

Bounded review admission rejects overload; judge streaming has separate bounded admission and replay. There is no synchronous full-graph neural computation or external LLM on the payment path. The local feature adapter recomputes exact small-world histories; a production feature store and authorized event ingestion remain pilot work.

## Roles and integration

- Customer: signed HttpOnly session cookie; owns sandbox worlds and private derived checks.
- Judge: expiring read-only grant; sanitized review/trace export; no payer privileges.
- Recipient: only its own dummy balance and matching incoming transfers.
- Operator: separate `MAYA_OPERATOR_KEY`, 32+ random characters. Review/approval are bound to current review; approval does not bypass a hold timer.
- Partner: separate `MAYA_PARTNER_KEY`. Set `MAYA_PARTNER_MODEL_DIR` and `MAYA_PARTNER_SOURCE` only after an authorized validation process. Its bundle manifest must match the source and hash a `validation-report.json` with `approved_for_shadow_operation`. This is operator-controlled readiness evidence, not a regulatory certification. The endpoint is shadow advice; the partner still owns authorization and settlement.

Keep operator and partner keys empty unless their owner and purpose are established. Provision secrets on the server, not in conversation or committed files. Production requires an HTTPS public origin and persistent 32+ character session secret; missing configuration stops startup.

## Upgrade, backup and rollback

Before upgrading, record the release commit/tag and image digest, model/schema/calibration manifests, and migration version. Keep the same `.env` privately. Stop writes for coordinated database/model restoration.

On the Linux Docker host:

```sh
mkdir -p backups
docker compose exec -T db pg_dump -U maya -Fc maya > backups/maya.dump
```

Encrypt and restrict backups; copy them off the server. Test restoration into a **separate empty database**, verify review signatures and ledger conservation, then rehearse the release. Never overwrite the live database to test a backup. Retention/deletion policy also applies to backups.

For a consistent local SQLite copy:

```sh
python scripts/backup_product.py --database data/v4/product.sqlite --out data/checkpoints/product-backup.sqlite
```

`scripts/versions.py list` shows existing recovery points. Its restore command creates a new branch and refuses dirty work. Code rollback does not restore models or database state. V4's PostgreSQL schema migration is additive; do not remove audit tables to roll back the UI. Preserve matching signing keys and review versions, or keep old reviews readable but require a new compatible review before execution.

## Acceptance and honest remaining gates

Run pytest and policy self-tests; run PostgreSQL integration with `MAYA_TEST_DATABASE_URL`; run the three-context browser test; then measure full-path load on a separate database. Read `V4_RELEASE_STATUS.md` for results and gaps.

Public hosting cannot be confirmed until the server/account/domain exist and the image, database and TLS path have been exercised there. Native-language review, five independent human usability sessions, authorized bank datasets/integration, sustained/distributed capacity tests and operational certification cannot be replaced by automated tests.
