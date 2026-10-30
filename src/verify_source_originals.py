"""Reconstruct projection directly from private exact JSON using SQLite JSON1."""

import argparse, hashlib, json, sqlite3
from pathlib import Path


def main(private, root):
    receipts = json.loads((private / "receipts.json").read_text())
    public = json.loads((root / "data/source_receipts.json").read_text())
    rows = json.loads((root / "data/paired_counts.json").read_text())
    ledger = json.loads((root / "data/qualification_ledger.json").read_text())
    con = sqlite3.connect(":memory:")
    con.execute(
        "create table cells(package text,d text,category text,n integer, primary key(package,d,category))"
    )
    conditions = 0
    for p in public:
        r = next(
            r for r in receipts if r["package"] == p["package"] and r["status"] == 200
        )
        raw = (private / r["private_body"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == r["sha256"] == p["sha256"]
        conditions += 1
        text = raw.decode("utf-8")
        identity = con.execute(
            "select json_extract(?,'$.package'),json_extract(?,'$.type')", (text, text)
        ).fetchone()
        assert identity == (p["package"], "overall_downloads")
        conditions += 1
        values = con.execute(
            "select json_extract(value,'$.date'),json_extract(value,'$.category'),json_extract(value,'$.downloads'),json_type(value,'$.downloads') from json_each(?,'$.data')",
            (text,),
        ).fetchall()
        for d, c, n, t in values:
            assert (
                t == "integer" and n >= 0 and c in ("with_mirrors", "without_mirrors")
            )
            conditions += 1
            con.execute("insert into cells values(?,?,?,?)", (p["package"], d, c, n))
        l = next(x for x in ledger if x["package"] == p["package"])
        assert l["source_cells"] == len(values) and l["source_dates"] == len(
            {d for d, c, n, t in values}
        )
        conditions += 1
    for r in rows:
        values = dict(
            con.execute(
                "select category,n from cells where package=? and d=?",
                (r["package"], r["date"]),
            )
        )
        assert r["with_mirrors"] == values.get("with_mirrors") and r[
            "without_mirrors"
        ] == values.get("without_mirrors")
        conditions += 2
    assert len(rows) == 1800 and len(public) == 12
    conditions += 2
    output = dict(
        status="PASS_PRIVATE_NATIVE_SQLITE_PROJECTION",
        conditions=conditions,
        source_entities=len(public),
        source_cells=con.execute("select count(*) from cells").fetchone()[0],
        projected_rows=len(rows),
        source_bytes=sum(r["bytes"] for r in receipts),
    )
    print(json.dumps(output))
    (root / "data/source_verification.json").write_bytes(
        (json.dumps(output, indent=2) + "\n").encode()
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--private", required=True, type=Path)
    a = p.parse_args()
    main(a.private, Path(__file__).resolve().parents[1])
