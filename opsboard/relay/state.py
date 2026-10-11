import asyncio
import json
import time
import uuid

STATUSES = {"ok", "warn", "crit", "unknown"}


class State:
    def __init__(self, cfg):
        self.cfg = cfg
        self.tiles = {}
        self.cards = {}
        self.clients = set()
        self.lock = asyncio.Lock()

    # ---- snapshot ----
    def snapshot(self):
        self._expire_cards()
        return {
            "type": "state",
            "board_name": self.cfg.get("board_name"),
            "demo": self.cfg.get("demo", False),
            "tiles": list(self.tiles.values()),
            "cards": sorted(self.cards.values(), key=lambda c: c["created"], reverse=True),
            "decks": self.public_decks(),
            "ts": time.time(),
        }

    def public_decks(self):
        out = []
        for d in self.cfg.get("decks", []):
            out.append({
                "name": d.get("name", "Deck"),
                "buttons": [
                    {
                        "label": b.get("label", b.get("action", "?")),
                        "action": b.get("action"),
                        "icon": b.get("icon", ""),
                        "confirm": bool(b.get("confirm", False)),
                        "tile": b.get("tile"),
                    }
                    for b in d.get("buttons", [])
                ],
            })
        return out

    # ---- tiles ----
    def upsert_tile(self, tid, title=None, value=None, status=None, detail=None, kind=None, extra=None):
        t = self.tiles.get(tid, {"id": tid, "title": tid, "value": "", "status": "unknown", "detail": ""})
        if title is not None:
            t["title"] = title
        if value is not None:
            t["value"] = str(value)
        if status is not None:
            t["status"] = status if status in STATUSES else "unknown"
        if detail is not None:
            t["detail"] = detail
        if kind is not None:
            t["kind"] = kind
        if extra:
            t.update(extra)
        t["updated"] = time.time()
        self.tiles[tid] = t
        self.broadcast({"type": "tile", "tile": t})
        return t

    def remove_tile(self, tid):
        if tid in self.tiles:
            del self.tiles[tid]
            self.broadcast({"type": "tile_removed", "id": tid})

    # ---- cards ----
    def push_card(self, title, body="", level="info", ttl_seconds=30, speak=False, speak_text=None):
        if level not in ("info", "warn", "crit"):
            level = "info"
        card = {
            "id": uuid.uuid4().hex[:10],
            "title": title or "",
            "body": body or "",
            "level": level,
            "ttl": int(ttl_seconds or 30),
            "created": time.time(),
            "speak": bool(speak),
        }
        if speak:
            card["speak_text"] = speak_text or f"{title}. {body}".strip(". ")
        self.cards[card["id"]] = card
        self._expire_cards()
        self.broadcast({"type": "card", "card": card})
        return card

    def _expire_cards(self):
        now = time.time()
        for cid in [c for c, v in self.cards.items() if v["created"] + v["ttl"] < now]:
            del self.cards[cid]

    def say(self, text):
        self.broadcast({"type": "say", "text": text})

    # ---- websocket fanout ----
    def broadcast(self, msg):
        data = json.dumps(msg)
        for ws in list(self.clients):
            q = getattr(ws, "_queue", None)
            if q is not None:
                try:
                    q.put_nowait(data)
                except asyncio.QueueFull:
                    pass
