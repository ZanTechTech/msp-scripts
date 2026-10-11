import asyncio
import io
import json
import logging
import os
import time

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, Header, Query
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles

from .state import State
from .actions import run_action
from .pollers import start_pollers, kuma_webhook
from . import demo as demo_mod

log = logging.getLogger("relay")
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

# 1x1 grey JPEG for demo/offline camera snapshots
_PLACEHOLDER_JPG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffc0000b080001000101011100ffc40014000100000000000000000000000000000008ffc40014100100000000000000000000000000000000ffda0008010100003f00548fffd9")


def create_app(cfg):
    app = FastAPI(title="opsboard relay", docs_url=None, redoc_url=None)
    state = State(cfg)
    app.state.board = state
    app.state.tasks = []
    app.state.bi = None
    TOKEN = cfg["token"]

    def check(token):
        if token != TOKEN:
            raise HTTPException(401, "bad token")

    @app.on_event("startup")
    async def _startup():
        if cfg.get("demo"):
            demo_mod.seed(state)
            app.state.tasks.append(asyncio.create_task(demo_mod.flipper(state, cfg.get("demo_flip_seconds", 45))))
        else:
            tasks, bi = start_pollers(state)
            app.state.tasks.extend(tasks)
            app.state.bi = bi
        app.state.tasks.append(asyncio.create_task(_card_sweeper()))

    async def _card_sweeper():
        while True:
            await asyncio.sleep(5)
            before = set(state.cards)
            state._expire_cards()
            for cid in before - set(state.cards):
                state.broadcast({"type": "card_removed", "id": cid})

    # ---------- REST ----------
    @app.get("/api/state")
    async def get_state():
        return state.snapshot()

    @app.post("/api/push")
    async def push(req: Request, x_board_token: str = Header(default="")):
        check(x_board_token)
        b = await req.json()
        card = state.push_card(b.get("title", ""), b.get("body", ""), b.get("level", "info"),
                               b.get("ttl_seconds", 30), bool(b.get("speak", False)))
        return {"ok": True, "card": card}

    @app.post("/api/say")
    async def say(req: Request, x_board_token: str = Header(default="")):
        check(x_board_token)
        b = await req.json()
        text = str(b.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "text required")
        state.say(text)
        return {"ok": True}

    @app.post("/api/tile")
    async def tile(req: Request, x_board_token: str = Header(default="")):
        check(x_board_token)
        b = await req.json()
        tid = b.get("id")
        if not tid:
            raise HTTPException(400, "id required")
        t = state.upsert_tile(tid, b.get("title"), b.get("value"), b.get("status"), b.get("detail"), b.get("kind"))
        return {"ok": True, "tile": t}

    @app.delete("/api/tile/{tid}")
    async def del_tile(tid: str, x_board_token: str = Header(default="")):
        check(x_board_token)
        state.remove_tile(tid)
        return {"ok": True}

    @app.post("/api/action/{action_id}")
    async def action(action_id: str, x_board_token: str = Header(default="")):
        check(x_board_token)
        res = await run_action(state, action_id)
        label = action_id
        for d in cfg.get("decks", []):
            for btn in d.get("buttons", []):
                if btn.get("action") == action_id:
                    label = btn.get("label", action_id)
        if res.get("ok"):
            r = res.get("result")
            body = r if isinstance(r, str) else json.dumps(r)[:300]
            state.push_card(f"✓ {label}", body, "info", 15)
        else:
            state.push_card(f"✗ {label}", res.get("error") or f"HTTP {res.get('status')}: {str(res.get('result'))[:300]}", "warn", 30)
        return res

    @app.post("/api/webhook/kuma")
    async def webhook_kuma(req: Request, x_board_token: str = Header(default=""), token: str = Query(default="")):
        check(x_board_token or token)
        payload = await req.json()
        kuma_webhook(state, payload)
        return {"ok": True}

    @app.post("/api/ask")
    async def ask(req: Request, x_board_token: str = Header(default="")):
        check(x_board_token)
        b = await req.json()
        text = str(b.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "text required")
        state.push_card("You said", text, "info", 20)
        url = cfg.get("ask_webhook_url")
        reply = "No assistant wired. Set ask_webhook_url in config.yaml."
        if url:
            try:
                async with httpx.AsyncClient(timeout=float(cfg.get("ask_timeout", 60))) as c:
                    r = await c.post(url, json={"text": text, "source": "opsboard"},
                                     headers={"Authorization": f"Bearer {cfg.get('ask_webhook_token', '')}"})
                try:
                    j = r.json()
                    reply = j.get("reply") or j.get("text") or j.get("answer") or r.text
                except Exception:
                    reply = r.text
            except Exception as e:
                reply = f"Assistant error: {type(e).__name__}: {e}"
        state.push_card("Assistant", reply, "info", 45, speak=True, speak_text=reply)
        return {"ok": True, "reply": reply}

    @app.get("/api/cam/{name}.jpg")
    async def cam(name: str):
        if cfg.get("demo") or not app.state.bi:
            return Response(_PLACEHOLDER_JPG, media_type="image/jpeg",
                            headers={"Cache-Control": "no-store"})
        try:
            r = await app.state.bi.snapshot(name)
            return Response(r.content, media_type=r.headers.get("content-type", "image/jpeg"),
                            headers={"Cache-Control": "no-store"})
        except Exception as e:
            raise HTTPException(502, f"snapshot failed: {e}")

    # ---------- WebSocket ----------
    @app.websocket("/api/ws")
    async def ws_endpoint(ws: WebSocket, token: str = Query(default="")):
        if token != TOKEN:
            await ws.close(code=4401)
            return
        await ws.accept()
        ws._queue = asyncio.Queue(maxsize=500)
        state.clients.add(ws)
        await ws.send_text(json.dumps(state.snapshot()))

        async def sender():
            while True:
                try:
                    data = await asyncio.wait_for(ws._queue.get(), timeout=20)
                    await ws.send_text(data)
                except asyncio.TimeoutError:
                    await ws.send_text(json.dumps({"type": "ping", "ts": time.time()}))

        send_task = asyncio.create_task(sender())
        try:
            while True:
                msg = await ws.receive_text()
                try:
                    j = json.loads(msg)
                except Exception:
                    continue
                if j.get("type") == "pong" or j.get("type") == "ping":
                    if j.get("type") == "ping":
                        await ws.send_text(json.dumps({"type": "pong"}))
                elif j.get("type") == "resync":
                    await ws.send_text(json.dumps(state.snapshot()))
        except WebSocketDisconnect:
            pass
        except Exception as e:
            log.debug("ws error: %s", e)
        finally:
            send_task.cancel()
            state.clients.discard(ws)

    # ---------- static ----------
    @app.get("/")
    async def index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"), headers={"Cache-Control": "no-cache"})

    app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
    return app
