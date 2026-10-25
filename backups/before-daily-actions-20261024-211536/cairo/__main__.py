"""python -m cairo"""
import argparse
from cairo.api import Server
from cairo.config import Settings


def main(open_browser: bool = False):
    parser = argparse.ArgumentParser(description="Cairo · local personal AI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        server = Server((args.host, args.port), Settings.from_env())
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Cairo: {exc}\n")
    print(f"Cairo: http://{args.host}:{server.server_port} · {server.app.settings.provider}", flush=True)
    if open_browser:
        import webbrowser
        from cairo.integrations.desktop_control import resolve_app
        url = f"http://{args.host}:{server.server_port}"
        try:
            executable = resolve_app("chrome")
            webbrowser.BackgroundBrowser(str(executable)).open(url)
        except OSError:
            webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nEncerrando Cairo...", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
