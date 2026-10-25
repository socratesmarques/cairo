"""Desktop entry point: starts the local service and opens its browser UI."""
from cairo.__main__ import main as serve


def main():
    serve(open_browser=True)
