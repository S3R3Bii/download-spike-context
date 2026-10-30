"""Project exact cached API entities; never score final outcomes here."""

import hashlib, json, argparse
from pathlib import Path
from downloads import parse, project, calendar


def save(p, obj):
    p.write_bytes((json.dumps(obj, indent=2, allow_nan=False) + "\n").encode())


def main(private):
    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root / "data/source_plan.json").read_text())
    captures = json.loads((private / "receipts.json").read_text())
    rows = []
    ledger = []
    public = []
    assert len({r["package"] for r in captures if r["status"] == 200}) == 12
    for p in plan["packages"]:
        matches = [
            r for r in captures if r["package"] == p["package"] and r["status"] == 200
        ]
        assert len(matches) == 1
        r = matches[0]
        raw = (private / r["private_body"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == r["sha256"]
        cells = parse(raw, p["package"])
        projection = project(cells, p["package"], plan)
        paired = sum(x["state"] == "paired" for x in projection)
        expected = set(calendar(plan["start"], plan["end"]))
        outside = [
            dict(date=d, category=c, downloads=v)
            for (d, c), v in sorted(cells.items())
            if d not in expected
        ]
        ledger.append(
            dict(
                package=p["package"],
                phase=p["phase"],
                source_cells=len(cells),
                source_dates=len({d for d, c in cells}),
                paired_window_dates=paired,
                missing_window_dates=[
                    r["date"] for r in projection if r["state"] != "paired"
                ],
                outside_window_cells=outside,
            )
        )
        assert paired >= plan["minimum_paired_dates"], "paired coverage gate"
        public.append({k: v for k, v in r.items() if k != "private_body"})
        rows.extend(projection)
    save(root / "data/paired_counts.json", rows)
    save(root / "data/qualification_ledger.json", ledger)
    save(root / "data/source_receipts.json", public)
    print(
        json.dumps(
            dict(
                status="PASS_SOURCE_PROJECTION",
                packages=len(ledger),
                projected_rows=len(rows),
                source_bytes=sum(r["bytes"] for r in captures),
                coverage=[(x["package"], x["paired_window_dates"]) for x in ledger],
            )
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--private", required=True, type=Path)
    main(p.parse_args().private)
