"""Loopback-only FastAPI boundary. The web client never submits scores/features."""
import asyncio
import json
import secrets
import time
import sqlite3
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt
from starlette.middleware.trustedhost import TrustedHostMiddleware


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorldInput(Input):
    seed: StrictInt
    preset: str = "everyday"


class IntentInput(Input):
    recipient: StrictInt
    amount_paise: StrictInt
    text: str = ""
    consent: StrictBool = False


class ReviewInput(Input):
    parent: str | None = None


class ExecuteInput(Input):
    review_id: str
    confirmed: StrictBool = False
    authorization: str


class ControlInput(Input):
    operation: str
    payment_id: str | None = None
    account: StrictInt | None = None
    seconds: StrictInt = 0
    review_id: str | None = None
    provider: str | None = None
    provider_state: str | None = None


class ShareInput(Input):
    account: StrictInt


class ConsentInput(Input):
    enabled: StrictBool


class GrantInput(Input):
    role: str


class ActionInput(Input):
    operation: str
    payment_id: str | None = None
    review_id: str | None = None


def create_app(service, controller_key=None, demo_docs=False):
    app = FastAPI(title="MAYA local payment simulator", docs_url="/api/docs" if demo_docs else None,
                  redoc_url=None, openapi_url="/api/openapi.json" if demo_docs else None)
    controller_key = controller_key or secrets.token_urlsafe(32)
    budgets = defaultdict(deque)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    web = Path(__file__).resolve().parents[1] / "web"

    @app.middleware("http")
    async def local_session(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
            return JSONResponse({"detail": "Cross-origin requests are disabled"}, status_code=403)
        owner = request.cookies.get("maya_session")
        new = not owner or len(owner) != 64 or any(c not in "0123456789abcdef" for c in owner)
        request.state.owner = secrets.token_hex(32) if new else owner
        request.state.request_id = secrets.token_hex(16)
        started = time.perf_counter()
        if request.method not in ("GET", "HEAD"):
            try:
                if int(request.headers.get("content-length", "0")) > 16384:
                    return JSONResponse({"detail": "Payload too large"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid content length"}, status_code=400)
            if len(await request.body()) > 16384:
                return JSONResponse({"detail": "Payload too large"}, status_code=413)
            if len(budgets) > 2048:
                cutoff = time.monotonic() - 60
                for stale in [k for k, v in budgets.items() if not v or v[-1] < cutoff]:
                    del budgets[stale]
            # One local network identity plus per-session budget; sessions cannot bypass global limit.
            for key, maximum in (("local-mutations", 300), (request.state.owner, 90)):
                q = budgets[key]
                now = time.monotonic()
                while q and q[0] < now - 60:
                    q.popleft()
                if len(q) >= maximum:
                    return JSONResponse({"detail": "Too many requests; retry shortly"}, status_code=429,
                                        headers={"Retry-After": "60"})
                q.append(now)
        response = await call_next(request)
        if new:
            response.set_cookie("maya_session", request.state.owner, httponly=True, samesite="strict",
                                secure=request.url.scheme == "https", max_age=604800)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Server-Timing"] = f"request;dur={(time.perf_counter() - started) * 1000:.2f}"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        ancestors = "'self'" if demo_docs and request.url.path == "/qa/wallet" else "'none'"
        response.headers["Content-Security-Policy"] = f"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors {ancestors}; base-uri 'none'"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(sqlite3.OperationalError)
    async def database_busy(request, error):
        return JSONResponse({"detail": "Storage temporarily unavailable. Recheck payment status before retrying."},
                            status_code=503, headers={"Retry-After": "1"})

    def controller(request):
        supplied = request.headers.get("x-maya-controller", "")
        if not supplied or not secrets.compare_digest(supplied, controller_key):
            from fastapi import HTTPException
            raise HTTPException(403, "Controller access required; use the key printed by run_demo.py")

    def access(request):
        return request.headers.get("x-maya-access", "")

    @app.get("/api/health")
    def health():
        ready = getattr(service.model, "ready", True)
        return JSONResponse({"ready": ready, "model_version": service.model.version, "mode": "dummy-local-only",
                             "degraded_policy": "block authorization until a successful fresh review"}, status_code=200 if ready else 503)

    @app.post("/api/worlds")
    def world(data: WorldInput, request: Request):
        return service.create_world(request.state.owner, data.seed, data.preset)

    @app.get("/api/worlds/{wid}")
    def read(wid: str, request: Request):
        return service.read_world(wid, request.state.owner)

    @app.post("/api/worlds/{wid}/intents")
    def intent(wid: str, data: IntentInput, request: Request):
        return service.intent(wid, request.state.owner, data.recipient, data.amount_paise, data.text, data.consent)

    @app.put("/api/worlds/{wid}/intents/{pid}")
    def change(wid: str, pid: str, data: IntentInput, request: Request):
        return service.intent(wid, request.state.owner, data.recipient, data.amount_paise, data.text, data.consent, pid)

    @app.post("/api/worlds/{wid}/intents/{pid}/review")
    def review(wid: str, pid: str, data: ReviewInput, request: Request):
        try:
            return service.review(wid, request.state.owner, pid, data.parent, request.state.request_id)
        except ValueError:
            raise
        except Exception:
            return JSONResponse({"detail": "Evaluation unavailable. No payment was sent; check server diagnostics."}, status_code=503)

    @app.post("/api/worlds/{wid}/intents/{pid}/execute")
    def execute(wid: str, pid: str, data: ExecuteInput, request: Request):
        return service.execute(wid, request.state.owner, pid, data.review_id, data.confirmed, data.authorization)

    @app.post("/api/worlds/{wid}/intents/{pid}/cancel")
    def cancel(wid: str, pid: str, request: Request):
        return service.cancel(wid, request.state.owner, pid)

    @app.get("/api/worlds/{wid}/reviews/{rid}")
    def replay(wid: str, rid: str, request: Request, recompute: bool = False):
        return service.replay(wid, request.state.owner, rid, recompute)

    @app.post("/api/worlds/{wid}/control")
    def control(wid: str, data: ControlInput, request: Request):
        controller(request)
        return service.control(wid, request.state.owner, data.operation, data.payment_id, data.account, data.seconds, data.review_id, data.provider, data.provider_state)

    @app.post("/api/worlds/{wid}/sharing")
    def sharing(wid: str, data: ShareInput, request: Request):
        return service.share(wid, request.state.owner, data.account)

    @app.post("/api/worlds/{wid}/sharing/revoke")
    def revoke(wid: str, request: Request):
        return service.revoke_sharing(wid, request.state.owner)

    @app.post("/api/worlds/{wid}/contact-consent")
    def consent(wid: str, data: ConsentInput, request: Request):
        return service.contact_consent(wid, request.state.owner, data.enabled)

    @app.delete("/api/worlds/{wid}")
    def delete(wid: str, request: Request):
        return service.delete_world(wid, request.state.owner)

    @app.get("/api/worlds/{wid}/reviews/{rid}/bundle")
    def bundle(wid: str, rid: str, request: Request):
        return service.bundle(wid, request.state.owner, rid)

    @app.get("/api/controller/worlds")
    def controlled_worlds(request: Request):
        controller(request)
        with service.lock:
            return [dict(id=r[0], seed=json.loads(r[1])["seed"], preset=json.loads(r[1])["preset"])
                    for r in service.db.execute("SELECT id,body FROM sim_world ORDER BY rowid DESC LIMIT 100")]

    @app.post("/api/controller/worlds/{wid}/grants")
    def grants(wid: str, data: GrantInput, request: Request):
        controller(request)
        return service.provision(wid, data.role)

    @app.post("/api/controller/worlds/{wid}/control")
    def independent_control(wid: str, data: ControlInput, request: Request):
        controller(request)
        with service.lock:
            row = service.db.execute("SELECT owner FROM sim_world WHERE id=?", (wid,)).fetchone()
            if row is None:
                raise ValueError("World not found")
            owner = row[0]
        return service.control(wid, owner, data.operation, data.payment_id, data.account, data.seconds, data.review_id, data.provider, data.provider_state)

    @app.post("/api/controller/worlds/{wid}/counterfactual")
    def counterfactual(wid: str, data: ReviewInput, request: Request):
        controller(request)
        with service.lock:
            row = service.db.execute("SELECT owner FROM sim_world WHERE id=?", (wid,)).fetchone()
            if row is None:
                raise ValueError("World not found")
        return service.counterfactual(wid, row[0], data.parent)

    @app.get("/api/access/view")
    def role_view(request: Request):
        return service.role_view(access(request))

    @app.post("/api/access/action")
    def role_action(data: ActionInput, request: Request):
        return service.role_action(access(request), data.operation, data.payment_id, data.review_id)

    @app.get("/api/worlds/{wid}/events")
    def events(wid: str, request: Request, after: int = 0):
        return service.events(wid, request.state.owner, after)

    @app.get("/api/worlds/{wid}/stream")
    async def stream(wid: str, request: Request, after: int = 0):
        owner = request.state.owner
        service.read_world(wid, owner)  # Authorization before response headers.
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            cursor = after

        async def messages():
            nonlocal cursor
            while not await request.is_disconnected():
                try:
                    committed = service.events(wid, owner, cursor)
                except ValueError:
                    return  # A payer may delete this synthetic world while streaming.
                for event in committed:
                    cursor = event["sequence"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                yield ": keepalive\n\n"
                await asyncio.sleep(0.4)
        return StreamingResponse(messages(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @app.get("/api/worlds/{wid}/ledger/{transfer}")
    def ledger(wid: str, transfer: str, request: Request):
        return service.ledger(wid, request.state.owner, transfer)

    @app.get("/api/observer")
    def observe(request: Request):
        return service.observe(access(request))

    @app.get("/console")
    def console():
        return FileResponse(web / "console.html")

    if demo_docs:
        @app.get("/qa/wallet")
        def qa_wallet():
            return FileResponse(web / "index.html")

    @app.get("/")
    @app.get("/recipient")
    def index():
        return FileResponse(web / "index.html")

    if web.exists():
        app.mount("/assets", StaticFiles(directory=web), name="assets")
    return app
