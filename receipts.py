"""Read publisher receipts locally; deliberately no remote administration endpoint."""

import argparse
import json
import re
import sqlite3
from pathlib import Path


def read_receipts(database, request_sha256, after=0):
    if not re.fullmatch(r"[a-f0-9]{64}", request_sha256) or after < 0:
        raise ValueError("Provide a SHA-256 digest and a nonnegative receipt cursor")
    uri = Path(database).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=1) as db:
        db.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in db.execute(
                "SELECT * FROM receipt WHERE request_sha256 = ? AND id > ? ORDER BY id LIMIT 100",
                (request_sha256, after),
            )
        ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    parser.add_argument("request_sha256")
    parser.add_argument("--after", type=int, default=0)
    args = parser.parse_args()
    try:
        rows = read_receipts(args.database, args.request_sha256, args.after)
    except (ValueError, sqlite3.Error):
        raise SystemExit(
            "Receipt query unavailable; check the private database and digest"
        ) from None
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
