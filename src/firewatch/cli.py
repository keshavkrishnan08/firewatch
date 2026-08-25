"""FIREWATCH command-line interface.

    firewatch build-demo            # build + run the offline synthetic event end-to-end
    firewatch replay --fire <id>    # reproduce the full picture for an event
    firewatch ingest --fire <id>    # pull live public feeds into the ontology for a real event
"""
from __future__ import annotations

import argparse


def main() -> None:
    p = argparse.ArgumentParser(prog="firewatch", description="Real-time wildfire common operating picture")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("build-demo", help="build + run the offline synthetic demo event")
    sp.add_argument("--fire", default="demo")
    sp.add_argument("--members", type=int, default=60)

    rp = sub.add_parser("replay", help="reproduce the full picture for an event")
    rp.add_argument("--fire", required=True)
    rp.add_argument("--members", type=int, default=60)

    ip = sub.add_parser("ingest", help="pull live public feeds into the ontology for a real event")
    ip.add_argument("--fire", required=True)
    ip.add_argument("--bbox", nargs=4, type=float, metavar=("MINLON", "MINLAT", "MAXLON", "MAXLAT"))
    ip.add_argument("--hours", type=int, default=24)

    fp = sub.add_parser("forecast", help="run the assimilating forecast on a stored event")
    fp.add_argument("--fire", required=True)
    fp.add_argument("--members", type=int, default=60)

    args = p.parse_args()

    if args.cmd in ("build-demo", "replay"):
        from firewatch.api.replay import run_replay

        run_replay(args.fire, n_members=args.members)
    elif args.cmd == "ingest":
        from firewatch.ingest.cli import ingest_event

        ingest_event(args.fire, bbox=tuple(args.bbox) if args.bbox else None, hours=args.hours)
    elif args.cmd == "forecast":
        from firewatch.api.replay import run_replay

        run_replay(args.fire, n_members=args.members)


if __name__ == "__main__":
    main()
