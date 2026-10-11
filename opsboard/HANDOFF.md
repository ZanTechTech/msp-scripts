# Handoff: deploy opsboard on JoshuaAI-Ubuntu

Written by a cloud Claude Code session that cannot reach the LAN. A Claude Code
session running on this node picks up from here.

## Facts
- Node: `JoshuaAI-Ubuntu`, LAN IP `192.168.1.32`, Ubuntu 26.04 LTS, Python 3.14.4.
- User at the console: `timothy` (has sudo). A dormant user `joshua` exists from the
  retired OpenClaw agent. Do not reuse it, its venvs, or its service-account files.
- Blue Iris instances are reachable over HTTPS at `https://<id>.wranglers.tech` (list via
  Prefect Horizon `bi_list_instances`); the office instance is `5005`. Office LAN cameras
  may also be reachable directly; Timothy knows the local BI address.
- Uptime Kuma sits behind Cloudflare Access (service-token headers). Shelly uses the
  cloud API with an auth key. Invoice Ninja is not needed for v1.
- The iPad kiosk is an iPad 7 on iPadOS 18, Safari, Guided Access.
- A hosted twin of this board already exists as a claude.ai artifact; this relay is the
  LAN version that keeps working when the WAN is down and can show camera snapshots.

## Do, in order
1. `sudo bash install.sh` from this folder. Fix anything Python 3.14 breaks
   (pydantic/uvicorn wheels) before moving on.
2. Confirm `systemctl status opsboard` is active and `curl localhost:8080/api/state` answers.
3. Have Timothy open `http://192.168.1.32:8080/?token=<token from /etc/opsboard/env>` on
   the iPad. Demo mode should render.
4. With Timothy, fill `/etc/opsboard/config.yaml` and `/etc/opsboard/env`: Blue Iris
   (office instance first), Kuma status page + CF Access token, Shelly auth key. Never
   paste secrets into chat; he edits `env` himself. Restart the service after each block
   and verify the tiles populate. Fix poller bugs as found; they are untested live.
5. Add a Kuma webhook notification pointing at
   `http://192.168.1.32:8080/api/webhook/kuma?token=<token>`.
6. Leave Shelly relay actions out of the decks unless Timothy asks; an "off" on a modem
   plug takes a site down.
7. Commit fixes back to this repo branch (`ccr-186af1a1-x4f18f`) so the cloud session can
   see them.

## Don't
- Don't expose port 8080 beyond the LAN. Don't put credentials in the web/ folder.
- Don't touch the retired Joshua gateway material or the cloudflared tunnel config.
