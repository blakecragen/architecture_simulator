#!/usr/bin/env python3
"""
appctl.py — the single entry point for the RTL CPU Simulator.

    python3 appctl.py                     # start the web server (default command)
    python3 appctl.py run                 # ... same thing, explicitly
    python3 appctl.py run --port 5051 --host 0.0.0.0 --debug
    python3 appctl.py test                # run the full pytest suite
    python3 appctl.py test -k riscv -q    # forward args straight to pytest
    python3 appctl.py --help

The real Flask application lives in ``api/app.py`` (routes, presets, the Core-C
compiler, etc.); this script just launches it so there is ONE obvious command to
run the project. The old ``app/flask_app.py`` (port-5000, Amaranth-era) server is
retired — do not use it.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_HOST = os.environ.get("HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("PORT", "5051"))  # matches api/app.py's default


def cmd_run(argv):
    """Start the web server."""
    import argparse
    parser = argparse.ArgumentParser(
        prog="appctl.py run",
        description="Start the RTL CPU Simulator web server (api/app.py).")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--debug", action="store_true",
                        help="enable Flask debug + reloader (or set FLASK_DEBUG=1)")
    args = parser.parse_args(argv)

    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from api.app import app  # the real server

    debug = args.debug or os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    print(f"RTL CPU Simulator  ->  http://{args.host}:{args.port}"
          f"   (debug {'on' if debug else 'off'})")
    app.run(host=args.host, port=args.port, debug=debug)
    return 0


def cmd_test(argv):
    """Run the pytest suite (extra args are forwarded to pytest)."""
    pytest_args = argv or ["tests/", "-q"]
    return subprocess.call([sys.executable, "-m", "pytest", *pytest_args], cwd=ROOT)


COMMANDS = {"run": cmd_run, "test": cmd_test}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # A leading help flag (before any subcommand) prints the overview.
    if argv and argv[0] in ("help", "-h", "--help"):
        print(__doc__)
        return 0
    # Default command is "run"; a leading token that isn't a flag selects one.
    cmd = "run"
    if argv and not argv[0].startswith("-"):
        cmd = argv.pop(0)
    if cmd not in COMMANDS:
        sys.stderr.write(
            f"appctl.py: unknown command '{cmd}'. "
            f"Use one of: {', '.join(COMMANDS)} (or --help).\n")
        return 2
    return COMMANDS[cmd](argv)


if __name__ == "__main__":
    raise SystemExit(main())
