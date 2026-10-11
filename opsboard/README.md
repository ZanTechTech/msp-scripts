# opsboard

A kiosk status board + programmable button deck for a small MSP. One old iPad in Safari (Guided Access) shows live tiles
(Blue Iris cameras, Uptime Kuma monitors, Shelly relays, HTTP probes, anything you POST), a tabbed deck of big buttons,
pushed message cards, and it can **speak**. A tiny Python relay on an Ubuntu VM holds every credential; the page holds none.
Anything on the LAN (a script, an AI assistant with `curl`) can push cards, tiles and speech onto the screen over the relay's REST API;
the page keeps a WebSocket open to the relay and resyncs after restarts.

```
iPad (Safari kiosk) <--WS/HTTP, token-->  relay (FastAPI, Ubuntu VM)  --creds-->  Blue Iris / Kuma / Shelly / ...
                                              ^ curl from scripts / AI
```

## 60-second install (Ubuntu 22.04 / 24.04)

```bash
git clone <this repo> opsboard && cd opsboard
sudo bash install.sh            # idempotent; re-run after git pull
```
It creates user `board`, installs to `/opt/opsboard` (venv), writes `/etc/opsboard/config.yaml` (from `config.example.yaml`)
and `/etc/opsboard/env` (random `BOARD_TOKEN`), installs `opsboard.service` (Restart=always) and prints the board URL + token.

Edit `/etc/opsboard/config.yaml` and `/etc/opsboard/env`, then `sudo systemctl restart opsboard`. Logs: `journalctl -u opsboard -f`.

Try it with no config/network: `python -m relay --demo` (token `demo`), open <http://localhost:8080/?token=demo>.

## Point the iPad at it

1. Safari → `http://<vm-ip>:8080/?token=<BOARD_TOKEN>` (token is stored in localStorage and stripped from the URL).
2. Tap **Tap to enable sound** once (Safari requires a gesture before audio/speech).
3. Share → **Add to Home Screen**, open it from there (full-screen, no Safari chrome).
4. Mic for push-to-talk: Settings → Safari → Microphone → Allow (or Ask), and allow on first use. Settings → Safari → Advanced → Website Data is where it ends up if you ever need to reset the stored token.
5. Guided Access: Settings → Accessibility → Guided Access → on, set a passcode; open the board, triple-click Home/side button → Start.
   Also set Display & Brightness → Auto-Lock → Never (Guided Access alone keeps the screen awake only on some iPadOS versions).
6. If the iPad sleeps and comes back, the page reconnects automatically and resyncs state.

## Pushing things onto the board

```bash
T=<BOARD_TOKEN>; B=http://<vm-ip>:8080
curl -s $B/api/state                                                     # read everything (no token needed)
curl -s -H "X-Board-Token: $T" -H 'Content-Type: application/json' -X POST $B/api/push \
  -d '{"title":"Ticket #4412","body":"ACME VPN down, Dave on it","level":"crit","ttl_seconds":120,"speak":true}'
curl -s -H "X-Board-Token: $T" -H 'Content-Type: application/json' -X POST $B/api/say -d '{"text":"Lunch is here"}'
curl -s -H "X-Board-Token: $T" -H 'Content-Type: application/json' -X POST $B/api/tile \
  -d '{"id":"backups","title":"Veeam","value":"3 failed","status":"warn","detail":"ACME-FS01 failed 02:10"}'
curl -s -H "X-Board-Token: $T" -X POST $B/api/action/shelly_shop_lights_toggle   # run a configured action
curl -s -H "X-Board-Token: $T" -X DELETE $B/api/tile/backups
curl -s -H "X-Board-Token: $T" -H 'Content-Type: application/json' -X POST $B/api/ask -d '{"text":"what is down?"}'
```
`level`: info | warn | crit (crit pulses + beeps). `status`: ok | warn | crit | unknown. Tiles with `kind: camera`
(or id `cam_*`) show a snapshot from `/api/cam/<name>.jpg`, proxied from Blue Iris by the relay.

### WebSocket
`ws://<vm-ip>:8080/api/ws?token=<BOARD_TOKEN>` sends `{type:"state",...}` on connect, then deltas: `tile`, `tile_removed`,
`card`, `card_removed`, `say`, `ping`. Send `{"type":"resync"}` to get the full state again.

## Integrations (config.yaml)

* **Uptime Kuma webhook** (instant): in Kuma, Settings → Notifications → Webhook, URL
  `http://<vm-ip>:8080/api/webhook/kuma?token=<BOARD_TOKEN>`, content type JSON, apply to all monitors.
  Each event updates the monitor tile and the "Uptime Kuma: N up / M down" summary, and DOWN events push a spoken crit card.
* **Uptime Kuma polling**: set `kuma.url` + `kuma.status_page_slug` (a public status page). Behind Cloudflare Access, add
  `headers: {CF-Access-Client-Id: "${CF_ACCESS_CLIENT_ID}", CF-Access-Client-Secret: "${CF_ACCESS_CLIENT_SECRET}"}` and put the values in `/etc/opsboard/env`.
* **Blue Iris**: `blueiris: {url: "http://bi-host:81", user: "${BI_USER}", password: "${BI_PASS}"}`. Use a BI user with LAN-only + no admin.
  Gives one tile per camera plus a summary, and snapshot proxying for the camera tiles.
* **Shelly Cloud**: `shelly: {server: "https://shelly-XX-eu.shelly.cloud", auth_key: "${SHELLY_AUTH_KEY}", devices: [{id, name, tile, channel}]}`.
  Server + key come from the Shelly app → User settings → Authorization cloud key. Toggle actions use
  `url: {server}/device/relay/control`, `data: {auth_key, id, channel, turn: toggle}`.
* **probes**: list of `{name, url, expect}` → ok/crit tile.
* **actions**: `{id: {method, url, headers, json|data, toggle_tile}}`; any string may use `${ENV_VAR}` from `/etc/opsboard/env`.
* **decks**: tabs of buttons; `confirm: true` = hold 1.5 s; `tile: <id>` makes the button show that tile's value/colour.
* **ask_webhook_url**: where push-to-talk transcripts (and `/api/ask`) are POSTed as `{text, source}`; the JSON `reply` (or text body) is shown and spoken.

## Security notes

* LAN only. Do not port-forward it; put it behind a VPN/Tailscale if you need remote access. No TLS is built in; put nginx/caddy in front if you want https (needed for mic on non-localhost origins in some browsers; Safari on iPad allows mic on http LAN origins only after a prompt — if it refuses, front it with https).
* Every mutating endpoint and the WebSocket require the shared `BOARD_TOKEN`. `GET /api/state` and `/api/cam/*.jpg` are read-only but unauthenticated so the kiosk page stays simple; anyone on the LAN can view status. Change the token in `/etc/opsboard/env` and restart.
* All credentials (Blue Iris, Shelly, Cloudflare) live in `/etc/opsboard/env` (mode 640, root:board) and only ever leave the VM toward the target service. The page never sees them: camera images are proxied, actions run server-side.
* The systemd unit runs as the unprivileged `board` user with `ProtectSystem=strict`.
