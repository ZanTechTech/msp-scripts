"""Optional background pollers. Each one is skipped if its config block is absent."""
import asyncio
import hashlib
import logging
import os
import time

import httpx

from .config import subst_env

log = logging.getLogger("relay.pollers")


def _interval(cfg, block):
    return float(block.get("poll_interval") or cfg.get("poll_interval") or 30)


async def _loop(name, interval, fn):
    while True:
        try:
            await fn()
        except Exception as e:
            log.warning("%s poller error: %s: %s", name, type(e).__name__, e)
        await asyncio.sleep(interval)


# ---------------- Blue Iris ----------------
class BlueIris:
    def __init__(self, state, block):
        self.state = state
        self.b = subst_env(block)
        self.url = self.b["url"].rstrip("/")
        self.session = None
        self.client = httpx.AsyncClient(timeout=15, verify=self.b.get("verify_tls", True))

    async def cmd(self, cmd, **kw):
        payload = {"cmd": cmd, **kw}
        if self.session:
            payload["session"] = self.session
        r = await self.client.post(self.url + "/json", json=payload)
        return r.json()

    async def login(self):
        r = await self.cmd("login")
        self.session = r.get("session")
        resp = hashlib.md5(f"{self.b['user']}:{self.session}:{self.b['password']}".encode()).hexdigest()
        r = await self.cmd("login", response=resp)
        if r.get("result") != "success":
            self.session = None
            raise RuntimeError(f"Blue Iris login failed: {r}")

    async def poll(self):
        if not self.session:
            await self.login()
        cams = await self.cmd("camlist")
        if cams.get("result") != "success":
            self.session = None
            await self.login()
            cams = await self.cmd("camlist")
        data = cams.get("data", [])
        n_ok = n_bad = 0
        for c in data:
            short = c.get("optionValue")
            if not short or short.startswith("@") or short.startswith("+") or c.get("group"):
                continue
            online = c.get("isOnline", True) and not c.get("isNoSignal", False)
            n_ok += online
            n_bad += not online
            self.state.upsert_tile(
                f"cam_{short}", title=c.get("optionDisplay", short),
                value="LIVE" if online else "NO SIGNAL", status="ok" if online else "crit",
                detail=f"{c.get('optionDisplay')} • {c.get('FPS', '?')} fps • {'rec' if c.get('isRecording') else 'idle'}",
                kind="camera", extra={"cam": short})
        st = await self.cmd("status")
        d = st.get("data", {}) if isinstance(st, dict) else {}
        cpu = d.get("cpu", "?")
        self.state.upsert_tile("blueiris", title="Blue Iris", value=f"{n_ok} up / {n_bad} down",
                               status="ok" if n_bad == 0 else "crit",
                               detail=f"CPU {cpu}% • mem {d.get('mem', '?')} • {len(data)} entries")

    async def snapshot(self, cam):
        if not self.session:
            await self.login()
        r = await self.client.get(f"{self.url}/image/{cam}", params={"q": 50, "s": 60},
                                  cookies={"session": self.session})
        if r.status_code == 401 or "image" not in r.headers.get("content-type", ""):
            await self.login()
            r = await self.client.get(f"{self.url}/image/{cam}", params={"q": 50, "s": 60},
                                      cookies={"session": self.session})
        return r


# ---------------- Uptime Kuma ----------------
async def kuma_poll(state, block):
    b = subst_env(block)
    url = b["url"].rstrip("/")
    slug = b["status_page_slug"]
    headers = {}
    for k, v in (b.get("headers") or {}).items():
        headers[k] = v
    async with httpx.AsyncClient(timeout=20, headers=headers) as c:
        page = (await c.get(f"{url}/api/status-page/{slug}")).json()
        hb = (await c.get(f"{url}/api/status-page/heartbeat/{slug}")).json()
    hbl = hb.get("heartbeatList", {})
    up = down = 0
    for group in page.get("publicGroupList", []):
        for m in group.get("monitorList", []):
            mid = str(m["id"])
            beats = hbl.get(mid, [])
            last = beats[-1] if beats else None
            status = "unknown"
            if last is not None:
                s = last.get("status")
                status = "ok" if s == 1 else "warn" if s in (2, 3) else "crit"
            up += status == "ok"
            down += status == "crit"
            state.upsert_tile(f"kuma_{mid}", title=m["name"], value="UP" if status == "ok" else "DOWN" if status == "crit" else status.upper(),
                              status=status, detail=(last or {}).get("msg", "") or f"ping {(last or {}).get('ping', '?')} ms",
                              kind="monitor", extra={"group": group.get("name")})
    state.upsert_tile("kuma", title="Uptime Kuma", value=f"{up} up / {down} down",
                      status="ok" if down == 0 else "crit", detail=f"status page: {slug}")


def kuma_webhook(state, payload):
    """Handle Uptime Kuma webhook notification JSON."""
    mon = payload.get("monitor") or {}
    hb = payload.get("heartbeat") or {}
    mid = str(mon.get("id") or mon.get("name") or "unknown")
    name = mon.get("name") or f"monitor {mid}"
    s = hb.get("status")
    status = "ok" if s == 1 else "warn" if s in (2, 3) else "crit" if s == 0 else "unknown"
    state.upsert_tile(f"kuma_{mid}", title=name, value="UP" if status == "ok" else "DOWN" if status == "crit" else status.upper(),
                      status=status, detail=hb.get("msg") or payload.get("msg") or "", kind="monitor")
    up = sum(1 for t in state.tiles.values() if t["id"].startswith("kuma_") and t["status"] == "ok")
    down = sum(1 for t in state.tiles.values() if t["id"].startswith("kuma_") and t["status"] == "crit")
    state.upsert_tile("kuma", title="Uptime Kuma", value=f"{up} up / {down} down", status="ok" if down == 0 else "crit",
                      detail=f"last event: {name} {'UP' if status == 'ok' else 'DOWN'}")
    if status == "crit":
        state.push_card(f"DOWN: {name}", hb.get("msg", ""), level="crit", ttl_seconds=120, speak=True,
                        speak_text=f"Alert. {name} is down.")
    elif status == "ok":
        state.push_card(f"UP: {name}", hb.get("msg", ""), level="info", ttl_seconds=30, speak=True,
                        speak_text=f"{name} is back up.")


# ---------------- Shelly Cloud ----------------
async def shelly_poll(state, block):
    b = subst_env(block)
    server = b["server"].rstrip("/")
    key = b["auth_key"]
    async with httpx.AsyncClient(timeout=15) as c:
        for dev in b.get("devices", []):
            r = await c.post(f"{server}/device/status", data={"auth_key": key, "id": dev["id"]})
            j = r.json()
            ds = (j.get("data") or {}).get("device_status") or {}
            online = (j.get("data") or {}).get("online", False)
            on = None
            if "relays" in ds:
                on = ds["relays"][dev.get("channel", 0)].get("ison")
            elif f"switch:{dev.get('channel', 0)}" in ds:
                on = ds[f"switch:{dev.get('channel', 0)}"].get("output")
            val = "OFFLINE" if not online else ("ON" if on else "OFF")
            state.upsert_tile(dev.get("tile") or f"shelly_{dev['id']}", title=dev.get("name", dev["id"]), value=val,
                              status="crit" if not online else ("ok" if on else "unknown"),
                              detail=f"Shelly {dev['id']} ch{dev.get('channel', 0)}", kind="relay")


# ---------------- HTTP probes ----------------
async def probe_poll(state, probes):
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
        for p in probes:
            p = subst_env(p)
            tid = p.get("id") or "probe_" + p["name"].lower().replace(" ", "_")
            t0 = time.time()
            try:
                r = await c.get(p["url"])
                ms = int((time.time() - t0) * 1000)
                exp = int(p.get("expect", 200))
                ok = r.status_code == exp
                state.upsert_tile(tid, title=p["name"], value=f"{r.status_code} • {ms} ms", status="ok" if ok else "crit",
                                  detail=f"GET {p['url']} expected {exp}", kind="probe")
            except Exception as e:
                state.upsert_tile(tid, title=p["name"], value="ERR", status="crit", detail=f"{type(e).__name__}: {e}", kind="probe")


def start_pollers(state):
    cfg = state.cfg
    tasks = []
    bi = None
    if cfg.get("blueiris"):
        bi = BlueIris(state, cfg["blueiris"])
        tasks.append(asyncio.create_task(_loop("blueiris", _interval(cfg, cfg["blueiris"]), bi.poll)))
    k = cfg.get("kuma") or {}
    if k.get("url") and k.get("status_page_slug"):
        tasks.append(asyncio.create_task(_loop("kuma", _interval(cfg, k), lambda: kuma_poll(state, k))))
    sh = cfg.get("shelly") or {}
    if sh.get("server") and sh.get("auth_key") and sh.get("devices"):
        tasks.append(asyncio.create_task(_loop("shelly", _interval(cfg, sh), lambda: shelly_poll(state, sh))))
    if cfg.get("probes"):
        tasks.append(asyncio.create_task(_loop("probes", float(cfg.get("poll_interval", 30)), lambda: probe_poll(state, cfg["probes"]))))
    return tasks, bi
