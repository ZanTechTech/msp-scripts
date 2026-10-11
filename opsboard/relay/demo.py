"""Demo mode: no network, plausible fake data, random monitor flips."""
import asyncio
import random

CAMS = [("front", "Front Door"), ("lot", "Parking Lot"), ("shop", "Shop Floor"), ("rack", "Server Rack"),
        ("back", "Back Entrance"), ("lobby", "Lobby")]
MONITORS = ["ACME - Firewall", "ACME - DC01", "ACME - M365 Mail", "Bayside Dental - Server", "Bayside - VPN",
            "Northgate - Web", "Northgate - RDS", "Office - Internet", "Office - NAS", "Hilltop - Backup",
            "Hilltop - Switch", "Pinecrest - PBX"]
RELAYS = [("shelly_shop_lights", "Shop Lights"), ("shelly_sign", "Front Sign"), ("shelly_rack_fan", "Rack Fan")]

DEMO_ACTIONS = {
    "cam_front_preset_1": {"demo": True, "demo_result": "Front Door cam moved to preset 1"},
    "kuma_pause_acme": {"demo": True, "demo_result": "Paused 3 ACME monitors for 60 min"},
    "kuma_resume_acme": {"demo": True, "demo_result": "Resumed 3 ACME monitors"},
    "shelly_shop_lights_toggle": {"demo": True, "toggle_tile": "shelly_shop_lights"},
    "shelly_sign_toggle": {"demo": True, "toggle_tile": "shelly_sign"},
    "shelly_rack_fan_toggle": {"demo": True, "toggle_tile": "shelly_rack_fan"},
    "unifi_reboot_ap": {"demo": True, "demo_result": "Reboot sent to Office-AP-2"},
    "gdms_reboot_phones": {"demo": True, "demo_result": "Reboot queued for 14 phones"},
    "bi_arm": {"demo": True, "demo_result": "Blue Iris profile set to Armed"},
    "bi_disarm": {"demo": True, "demo_result": "Blue Iris profile set to Disarmed"},
}

DEMO_DECKS = [
    {"name": "Morning", "buttons": [
        {"label": "Front Door Cam", "action": "cam_front_preset_1", "icon": "📷"},
        {"label": "Pause Kuma: ACME", "action": "kuma_pause_acme", "icon": "⏸", "confirm": True},
        {"label": "Resume Kuma: ACME", "action": "kuma_resume_acme", "icon": "▶️"},
        {"label": "Shop Lights", "action": "shelly_shop_lights_toggle", "icon": "💡", "tile": "shelly_shop_lights"},
        {"label": "Front Sign", "action": "shelly_sign_toggle", "icon": "🪧", "tile": "shelly_sign"},
        {"label": "Disarm BI", "action": "bi_disarm", "icon": "🔓", "confirm": True},
    ]},
    {"name": "Evening", "buttons": [
        {"label": "Arm BI", "action": "bi_arm", "icon": "🔒", "confirm": True},
        {"label": "Shop Lights", "action": "shelly_shop_lights_toggle", "icon": "💡", "tile": "shelly_shop_lights"},
        {"label": "Rack Fan", "action": "shelly_rack_fan_toggle", "icon": "🌀", "tile": "shelly_rack_fan"},
        {"label": "Reboot Office AP", "action": "unifi_reboot_ap", "icon": "📶", "confirm": True},
        {"label": "Reboot Phones", "action": "gdms_reboot_phones", "icon": "☎️", "confirm": True},
    ]},
]


def seed(state):
    cfg = state.cfg
    cfg["decks"] = DEMO_DECKS  # demo always uses the demo decks
    cfg.setdefault("actions", {})
    for k, v in DEMO_ACTIONS.items():
        cfg["actions"][k] = v  # demo actions win over config
    for short, name in CAMS:
        state.upsert_tile(f"cam_{short}", title=name, value="LIVE", status="ok",
                          detail=f"{name} • 15 fps • rec", kind="camera", extra={"cam": short})
    state.upsert_tile("blueiris", title="Blue Iris", value="6 up / 0 down", status="ok", detail="CPU 23% • 6 cameras")
    down_idx = 3
    for i, name in enumerate(MONITORS):
        down = i == down_idx
        state.upsert_tile(f"kuma_{i+1}", title=name, value="DOWN" if down else "UP", status="crit" if down else "ok",
                          detail="timeout of 48000ms exceeded" if down else f"ping {random.randint(8, 90)} ms", kind="monitor")
    _kuma_summary(state)
    for tid, name in RELAYS:
        on = tid != "shelly_rack_fan"
        state.upsert_tile(tid, title=name, value="ON" if on else "OFF", status="ok" if on else "unknown",
                          detail="Shelly Plus 1PM (demo)", kind="relay")
    state.upsert_tile("unifi", title="UniFi", value="2 sites • 1 offline", status="warn",
                      detail="Office-AP-2 offline 12 min", kind="summary")
    state.upsert_tile("gdms", title="GDMS Phones", value="14 / 15 online", status="warn",
                      detail="Pinecrest ext 204 unreachable", kind="summary")
    state.push_card("Demo mode", "No network; data is fake and one Kuma monitor flips every 45s.", level="info", ttl_seconds=60)


def _kuma_summary(state):
    up = sum(1 for t in state.tiles.values() if t["id"].startswith("kuma_") and t["status"] == "ok")
    down = sum(1 for t in state.tiles.values() if t["id"].startswith("kuma_") and t["status"] == "crit")
    state.upsert_tile("kuma", title="Uptime Kuma", value=f"{up} up / {down} down", status="ok" if down == 0 else "crit",
                      detail="status page: demo")


async def flipper(state, period=45):
    while True:
        await asyncio.sleep(period)
        i = random.randint(1, len(MONITORS))
        t = state.tiles.get(f"kuma_{i}")
        if not t:
            continue
        if t["status"] == "ok":
            state.upsert_tile(t["id"], value="DOWN", status="crit", detail="timeout of 48000ms exceeded")
            state.push_card(f"DOWN: {t['title']}", "timeout of 48000ms exceeded", level="crit", ttl_seconds=60,
                            speak=True, speak_text=f"Alert. {t['title']} is down.")
        else:
            state.upsert_tile(t["id"], value="UP", status="ok", detail=f"ping {random.randint(8, 90)} ms")
            state.push_card(f"UP: {t['title']}", "recovered", level="info", ttl_seconds=30, speak=True,
                            speak_text=f"{t['title']} is back up.")
        _kuma_summary(state)
