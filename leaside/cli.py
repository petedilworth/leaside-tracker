"""python -m leaside.cli {probe|ingest|build|status}"""
from __future__ import annotations

import argparse
import sys

from . import db, demo, discover, doctor, ingest, probe, render


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="leaside")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe", help="check every configured URL and write config/probe-report.md")
    ing = sub.add_parser("ingest", help="pull every runnable source into SQLite")
    ing.add_argument("--only", nargs="*", help="limit to these source ids")
    sub.add_parser("build", help="render site/index.html from SQLite")
    sub.add_parser("demo", help="load test fixtures so the site renders offline")
    sub.add_parser("discover", help="scan directory pages for association feeds")
    sub.add_parser("status", help="show what is in the database")
    sub.add_parser("doctor", help="write config/health-report.md")
    args = ap.parse_args(argv)

    if args.cmd == "probe":
        probe.run()
    elif args.cmd == "ingest":
        totals = ingest.run(only=set(args.only) if args.only else None)
        print(f"\n{totals['new']} new, {totals['seen']} seen, {totals['failed']} sources failed")
    elif args.cmd == "discover":
        print(f"Wrote {discover.run()}")
    elif args.cmd == "demo":
        n = demo.run()
        page = render.run(db_path=db.DEMO_DB, out_name="demo.html")
        print(f"Loaded {n} fixture items into {db.DEMO_DB} and wrote {page}")
    elif args.cmd == "build":
        print(f"Wrote {render.run()}")
    elif args.cmd == "doctor":
        print(f"Wrote {doctor.run()}")
    elif args.cmd == "status":
        conn = db.connect()
        for row in conn.execute(
            "SELECT source_id, COUNT(*) n, MIN(published_at) oldest, MAX(published_at) latest"
            " FROM items GROUP BY source_id ORDER BY n DESC"
        ):
            span = f"{str(row['oldest'])[:10]} to {str(row['latest'])[:10]}"
            print(f"{row['n']:>6}  {row['source_id']:<32} {span}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
