"""Start VisionPilot:  .venv/Scripts/python -m visionpilot   (from the laptop/ folder)."""
from __future__ import annotations

import argparse
import logging
from dataclasses import replace

import uvicorn

from .app import create_app
from .certs import ensure_cert, local_ipv4s
from .config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="VisionPilot laptop brain")
    parser.add_argument("--port", type=int, help="HTTPS port (default 8443)")
    parser.add_argument("--no-tls", action="store_true", help="plain HTTP (phone camera needs a Chrome flag)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    net = settings.net
    if args.port:
        net = replace(net, port=args.port)
    if args.no_tls:
        net = replace(net, tls=False)
    settings = replace(settings, net=net)

    scheme = "https" if net.tls else "http"
    print("\n=== VisionPilot ===")
    print(f"Dashboard (this laptop): {scheme}://localhost:{net.port}/")
    for ip in local_ipv4s():
        if ip != "127.0.0.1":
            print(f"Phone:                   {scheme}://{ip}:{net.port}/phone")
    print("The car starts KILLED - press ARM on the dashboard.\n")

    ssl = {}
    if net.tls:
        cert, key = ensure_cert(net.cert_dir)
        ssl = {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}
    # log_config=None keeps our basicConfig so visionpilot.* logs are shown next to uvicorn's
    uvicorn.run(
        create_app(settings),
        host=net.host,
        port=net.port,
        log_config=None,
        ws_max_size=2**21,
        **ssl,
    )


if __name__ == "__main__":
    main()
