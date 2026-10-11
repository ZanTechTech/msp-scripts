import asyncio
import json
import httpx
from .config import subst_env


async def run_action(state, action_id):
    cfg = state.cfg
    actions = cfg.get("actions", {})
    if action_id not in actions:
        return {"ok": False, "error": f"unknown action '{action_id}'"}
    a = subst_env(actions[action_id])
    if cfg.get("demo") or a.get("demo"):
        await asyncio.sleep(0.3)
        # demo shelly toggles flip the bound tile
        tile_id = a.get("toggle_tile")
        if tile_id and tile_id in state.tiles:
            t = state.tiles[tile_id]
            on = t.get("value") != "ON"
            state.upsert_tile(tile_id, value="ON" if on else "OFF", status="ok" if on else "unknown",
                              detail=f"Relay {'on' if on else 'off'} (demo)")
        return {"ok": True, "status": 200, "result": a.get("demo_result", f"{action_id} executed (demo)")}
    method = (a.get("method") or "POST").upper()
    url = a.get("url")
    if not url:
        return {"ok": False, "error": "action has no url"}
    headers = a.get("headers") or {}
    body = a.get("json")
    data = a.get("data")
    timeout = float(a.get("timeout", 15))
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=a.get("verify_tls", True)) as c:
            r = await c.request(method, url, headers=headers, json=body, data=data)
        text = r.text[:800]
        try:
            parsed = r.json()
        except Exception:
            parsed = None
        ok = 200 <= r.status_code < 300
        # Shelly: optimistic tile update on relay control
        tile_id = a.get("toggle_tile")
        if ok and tile_id and body and "turn" in str(body):
            pass
        return {"ok": ok, "status": r.status_code, "result": parsed if parsed is not None else text}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
