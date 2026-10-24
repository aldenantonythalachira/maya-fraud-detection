# Put Maya online

The demo website — `/app/` for phones, `/demo/` for the big screen — runs as one
small Docker web service (about 320 MB of memory). The recommended free host is
**Render**. (Hugging Face Spaces also works, but since late 2026 its Docker
Spaces need a PRO subscription; only static Spaces are free.)

This is the research/demo server (`src/api.py`). Ashrith's V4 product
(`run_demo.py`, `docs/DEPLOY_V4.md`) is a separate app with its own server.

## What gets deployed

`python scripts/build_space.py` assembles `dist/space/` (about 3 MB):

| Path | What |
|---|---|
| `src/` | the API and the model / policy code |
| `frontend/` | user app, judges' view, shared tokens, fonts, QR encoder |
| `models/` | the trained bundle: `xgb_model.json`, `conformal.json`, `model_meta.json`, `attack_results.json` |
| `serve.py` | starts uvicorn on `$PORT` (Render) or 7860 (Spaces), one worker, proxy headers trusted |
| `Dockerfile`, `requirements.txt`, `render.yaml`, `README.md` | from `deploy/space/` (slim dependencies: no Streamlit/Plotly/PyArrow/PyTorch) |

`dist/` is gitignored: the trained weights never go into the team repository.
They go only to the deploy target.

## Render (free)

**One-time setup**

1. Publish the bundle to a private deploy repository under your GitHub account
   (needs the logged-in `gh` CLI; the repository is created if missing):
   ```powershell
   .\.venv\Scripts\python.exe scripts/build_space.py --github YOUR_GITHUB/maya-site
   ```
2. Sign up at <https://render.com> with **"Sign in with GitHub"** and allow
   Render to access the `maya-site` repository (it's private, so grant access to
   it when GitHub asks).
3. In Render: **New → Blueprint**, pick `maya-site`, and **Apply**.
   `render.yaml` creates one free Docker web service called `maya` with a
   `/v1/health` health check. The first build takes a few minutes.
4. The site is at the service's address, e.g. `https://maya-xxxx.onrender.com`:
   - **`/demo/`** on the projector: shows a QR code and a room code
   - **`/app/`** on phones: scan the QR, or open the address and enter the code

**Updating:** rebuild and push with the same command. Render redeploys
automatically (`autoDeploy`). The deploy repository holds only build output, so
each push is a fresh force-pushed snapshot. If you retrained, first run
`python src/attack_sim.py --json-out models/attack_results.json` and re-pick the
scenarios (`python scripts/pick_scenarios.py`).

## Hugging Face Spaces (needs PRO for Docker)

```powershell
.\.venv\Scripts\python.exe -m pip install huggingface_hub
.\.venv\Scripts\hf.exe auth login          # paste a write token
.\.venv\Scripts\python.exe scripts/build_space.py --upload YOUR_NAME/maya [--private]
```
The site is then at `https://YOUR_NAME-maya.hf.space`. A private Space can only
be opened by your logged-in account.

## Run the exact bundle locally

```powershell
.\.venv\Scripts\python.exe scripts/build_space.py
cd dist\space
..\..\.venv\Scripts\python.exe serve.py     # http://127.0.0.1:7860/demo/
```

## Limits of free hosting

- Render's free service **sleeps after about 15 minutes without visitors**; the
  next visit wakes it (about a minute). Open `/demo/` a few minutes before a demo.
- **Demo rooms live in memory**: a restart or sleep clears them. The judges'
  view then shows a fresh code automatically; phones just scan again.
- One server process (rooms are in memory): fine for a demo room full of
  phones, not a production deployment.
- Per-visitor rate limits use the host proxy's `X-Forwarded-For`
  (`MAYA_TRUST_PROXY=1`).
- Everything is synthetic: no real payments or bank data, and MuleHunter, FRI,
  1930 and the chat/call signals are simulated.
- Anyone with the site's address can use it. The **code** stays private (the
  deploy repository is private), but the site itself is public once deployed.
