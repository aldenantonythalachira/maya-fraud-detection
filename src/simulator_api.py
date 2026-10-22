"""Loopback-only FastAPI boundary. The web client never submits scores/features."""
import asyncio
import json
import secrets
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
    review_id: str | None = None
    account: StrictInt | None = None
    seconds: StrictInt = 0


def create_app(service):
    app = FastAPI(title="MAYA local payment simulator", docs_url="/api/docs", redoc_url=None)
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
        response = await call_next(request)
        if new:
            response.set_cookie("maya_session", request.state.owner, httponly=True, samesite="strict", max_age=604800)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.get("/api/health")
    def health():
        return {"ready": True, "model_version": service.model.version, "mode": "dummy-local-only"}

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
            return service.review(wid, request.state.owner, pid, data.parent)
        except ValueError:
            raise
        except Exception:
            service.emit(wid, "review_failed", pid, error="Model or feature evaluation failed")
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
        return service.control(wid, request.state.owner, data.operation, data.payment_id, data.account, data.seconds, data.review_id)

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
                for event in service.events(wid, owner, cursor):
                    cursor = event["sequence"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                yield ": keepalive\n\n"
                await asyncio.sleep(0.4)
        return StreamingResponse(messages(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @app.get("/api/worlds/{wid}/ledger/{transfer}")
    def ledger(wid: str, transfer: str, request: Request):
        return service.ledger(wid, request.state.owner, transfer)

    @app.get("/api/observe/{token}")
    def observe(token: str):
        return service.observe(token)

    @app.get("/")
    def index():
        return FileResponse(web / "index.html")

    if web.exists():
        app.mount("/assets", StaticFiles(directory=web), name="assets")
    return app
