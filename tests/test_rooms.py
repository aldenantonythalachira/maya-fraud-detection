"""Demo rooms: judge screen <- phones, through the API (no trained model needed)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api
from risk_common import FEATURE_COLUMNS
from rooms import MAX_PHONES, RateLimiter, RoomError, Rooms, normalize_code


class FakeScorer:
    model_version, calibration_version = "fake-model", "fake-calibration"

    def score(self, values, explain=False):
        out = {"p_scam": 0.7, "conformal_set": "{fine, scam}", "reasons": ["r1"], "reason_features": ["d_R"]}
        if explain:
            out["explanation"] = {"contributions": [], "note": "fake"}
        return out

    def info(self):
        return {"model_version": "fake-model", "calibration_version": "fake", "conformal": {},
                "metrics": {}, "attacks": None}


class Clock:
    def __init__(self):
        self.t = 1_000.0

    def __call__(self):
        return self.t


def make(clock=None, **limits):
    rooms = Rooms(clock=clock or Clock())
    app = api.create_app(FakeScorer(), None, load_defaults=False, rooms=rooms, rate_limits=limits or None)
    return TestClient(app), rooms


def body(**extra):
    f = {c: 0.0 for c in FEATURE_COLUMNS}
    f.update(z_t=3.0, d_R=0.0)  # two hard groups -> hold under an unsure set
    return {"features": f, "amount_inr": 900.0, **extra}


def test_judge_creates_phone_joins_and_server_publishes():
    c, _ = make()
    room = c.post("/v1/rooms").json()
    assert len(room["code"]) == 6 and room["watch_token"] and room["room"]
    phone = c.post("/v1/rooms/join", json={"code": room["code"].lower()}).json()  # case-insensitive
    r = c.post("/v1/score", json=body(room=phone["publish_token"], explain=True,
                                      context={"scenario": "police", "payee": "Officer"}))
    assert r.status_code == 200 and r.json()["room_published"] is True
    events = c.get(f"/v1/rooms/{room['room']}/events",
                   params={"watch": room["watch_token"], "format": "json"}).json()
    (e,) = events["events"]
    assert e["seq"] == 1 and e["action"] == "hold" and e["context"]["payee"] == "Officer"
    assert e["amount_inr"] == 900.0 and e["explanation"]["note"] == "fake"
    assert events["status"]["phones"] == 1


def test_phone_cannot_inject_a_decision():
    c, _ = make()
    phone = c.post("/v1/rooms/join", json={"code": c.post("/v1/rooms").json()["code"]}).json()
    # extra fields such as an "action" are rejected by the request schema
    r = c.post("/v1/score", json=body(room=phone["publish_token"], action="release"))
    assert r.status_code == 422


def test_watch_token_is_required_and_read_only():
    c, _ = make()
    room = c.post("/v1/rooms").json()
    url = f"/v1/rooms/{room['room']}/events"
    assert c.get(url, params={"watch": "wrong", "format": "json"}).status_code == 403
    assert c.get(f"/v1/rooms/nope/events", params={"watch": room["watch_token"]}).status_code == 404
    assert c.post(url, json={}).status_code == 405  # no way to write through the watch side


def test_bad_or_missing_room_never_fails_the_score():
    c, _ = make()
    r = c.post("/v1/score", json=body(room="not-a-token"))
    assert r.status_code == 200 and r.json()["room_published"] is False
    assert c.post("/v1/score", json=body()).json()["room_published"] is None


def test_unknown_code_and_phone_cap():
    c, _ = make()
    assert c.post("/v1/rooms/join", json={"code": "ZZZZZZ"}).status_code == 404
    code = c.post("/v1/rooms").json()["code"]
    for _ in range(MAX_PHONES):
        assert c.post("/v1/rooms/join", json={"code": code}).status_code == 200
    assert c.post("/v1/rooms/join", json={"code": code}).status_code == 409


def test_rooms_expire():
    clock = Clock()
    c, rooms = make(clock)
    room = c.post("/v1/rooms").json()
    phone = c.post("/v1/rooms/join", json={"code": room["code"]}).json()
    clock.t += rooms.ttl_s + 1
    assert c.post("/v1/rooms/join", json={"code": room["code"]}).status_code == 404
    assert c.post("/v1/score", json=body(room=phone["publish_token"])).json()["room_published"] is False
    assert c.get(f"/v1/rooms/{room['room']}", params={"watch": room["watch_token"]}).status_code == 404


def test_event_cursor_and_bounds():
    rooms = Rooms(clock=Clock())
    room = rooms.create()
    token = rooms.join(room["code"])["publish_token"]
    for i in range(130):
        rooms.publish(token, {"n": i})
    assert len(rooms.events(room["room"], room["watch_token"])) == 20          # replay window
    assert [e["seq"] for e in rooms.events(room["room"], room["watch_token"], 128)] == [129, 130]
    assert rooms.events(room["room"], room["watch_token"], 1)[0]["seq"] == 31  # only 100 kept


def test_room_cap():
    rooms = Rooms(clock=Clock(), max_rooms=2)
    rooms.create(), rooms.create()
    with pytest.raises(RoomError) as err:
        rooms.create()
    assert err.value.status == 503


def test_codes_are_unambiguous():
    rooms = Rooms(clock=Clock())
    codes = {rooms.create()["code"] for _ in range(200)}
    assert len(codes) == 200
    assert not any(ch in code for code in codes for ch in "0O1IL")
    assert normalize_code(" k7p-2qx ") == "K7P2QX"


def test_rate_limit_returns_429():
    c, _ = make(rooms=2)
    assert c.post("/v1/rooms").status_code == 201
    assert c.post("/v1/rooms").status_code == 201
    r = c.post("/v1/rooms")
    assert r.status_code == 429 and r.headers["retry-after"]


def test_rate_limiter_refills():
    t = [0.0]
    lim = RateLimiter(60, clock=lambda: t[0])
    assert all(lim.allow("a") for _ in range(60)) and not lim.allow("a")
    assert lim.allow("b")          # per client
    t[0] += 1.0                    # 60/min -> one token per second
    assert lim.allow("a") and not lim.allow("a")


def test_sse_stream_delivers_published_events():
    c, rooms = make()
    room = c.post("/v1/rooms").json()
    token = c.post("/v1/rooms/join", json={"code": room["code"]}).json()["publish_token"]
    c.post("/v1/score", json=body(room=token, context={"payee": "Mom"}))
    with c.stream("GET", f"/v1/rooms/{room['room']}/events", params={"watch": room["watch_token"]}) as s:
        assert s.headers["content-type"].startswith("text/event-stream")
        lines = []
        for line in s.iter_lines():
            lines.append(line)
            if line.startswith("data:"):
                break
    assert "id: 1" in lines and "event: payment" in lines
    assert '"payee": "Mom"' in lines[-1]
