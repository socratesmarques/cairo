"""python -m cairo"""

import argparse

from cairo.api import Server
from cairo.config import Settings


def main(open_browser: bool = False):
    parser = argparse.ArgumentParser(description="Cairo · local personal AI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    url = f"http://{args.host}:{args.port}"
    try:
        settings = Settings.from_env()
        if open_browser and args.host in {"127.0.0.1", "localhost"}:
            from cairo.desktop.instance import existing_instance, open_interface

            if existing_instance(url, settings.data_dir):
                print("Cairo já está aberto. Abrindo sua interface...", flush=True)
                open_interface(url)
                return
        server = Server((args.host, args.port), settings)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Cairo: {exc}\n")
    print(
        f"Cairo: http://{args.host}:{server.server_port} · {server.app.settings.provider}",
        flush=True,
    )
    if open_browser:
        from cairo.desktop.instance import open_interface

        url = f"http://{args.host}:{server.server_port}"
        open_interface(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nEncerrando Cairo...", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
