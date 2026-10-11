import argparse
import logging
import os

import uvicorn

from .config import load_config
from .app import create_app


def main():
    p = argparse.ArgumentParser(prog="relay", description="opsboard relay")
    p.add_argument("--config", default=os.environ.get("OPSBOARD_CONFIG", "config.yaml"))
    p.add_argument("--demo", action="store_true", help="no network, fake data")
    p.add_argument("--port", type=int)
    p.add_argument("--host")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(a.config, demo=a.demo)
    host = a.host or cfg.get("host", "0.0.0.0")
    port = a.port or int(cfg.get("port", 8080))
    app = create_app(cfg)
    print(f"[relay] board: http://{host}:{port}/?token={cfg['token']}  (demo={a.demo})")
    uvicorn.run(app, host=host, port=port, log_level="info", ws_ping_interval=20, ws_ping_timeout=20)


if __name__ == "__main__":
    main()
