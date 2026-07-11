"""
RETIRED legacy server — do not use.

This was the original port-5000, RISC-V-only, Amaranth-based UI server. It is
dead: it depends on the un-importable Amaranth stack (sim/cpu.py, sim/runner.py,
sim/execution/) and its templates/static assets no longer exist, so running it
only produced 500s.

The real simulator (all 3 ISAs x 5 models, the web UI, and the Core-C compiler)
is served by ``api/app.py``. Launch it from the repo root with the single entry
point:

    python3 appctl.py            # start the web server
    python3 appctl.py test       # run the test suite

This file no longer imports the dead stack and, if executed directly, just
prints the notice below and exits — so it can never be mistaken for the live
server again.
"""
import sys


def _retired() -> int:
    sys.stderr.write(
        "\n  app/flask_app.py is RETIRED and no longer serves the app.\n\n"
        "  Run the real simulator from the repo root:\n\n"
        "      python3 appctl.py\n\n"
        "  (full UI + Core-C compiler, served by api/app.py)\n\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(_retired())
