"""Independent SQLite calendar joins and 80-digit Decimal scoring."""

import argparse, json, sqlite3
from decimal import Decimal, localcontext
from pathlib import Path


def middle(values):
    s = sorted(values)
    n = len(s)
    return (s[(n - 1) // 2] + s[n // 2]) / 2


def decscore(current, prior):
    values = [(Decimal(n) + 1).ln() for n in prior]
    m = middle(values)
    return ((Decimal(current) + 1).ln() - m) / max(
        middle([abs(x - m) for x in values]), Decimal("0.1")
    )


def verify(root, phase):
    plan = json.loads((root / "data/source_plan.json").read_text())
    rows = json.loads((root / "data/paired_counts.json").read_text())
    results = json.loads((root / "results" / phase / "scores.json").read_text())
    summary = json.loads((root / "results" / phase / "summary.json").read_text())
    con = sqlite3.connect(":memory:")
    con.execute(
        "create table counts(package text,d text,w integer,u integer,primary key(package,d))"
    )
    con.executemany(
        "insert into counts values(?,?,?,?)",
        [
            (r["package"], r["date"], r["with_mirrors"], r["without_mirrors"])
            for r in rows
        ],
    )
    checked = 0

    def check(condition, context):
        nonlocal checked
        checked += 1
        if not condition:
            raise AssertionError(context)

    dates = [
        x[0]
        for x in con.execute(
            "with recursive days(d) as (select ? union all select date(d,'+1 day') from days where d<?) select d from days",
            (plan["start"], plan["end"]),
        )
    ]
    check(len(dates) == 150, "expected calendar")
    for r in rows:
        w, u = r["with_mirrors"], r["without_mirrors"]
        paired = w is not None and u is not None
        check(
            r["state"] == ("paired" if paired else "missing_pair"),
            ("state", r["package"], r["date"]),
        )
        if paired:
            check(type(w) is int and type(u) is int and w >= u >= 0, "nested")
            check(r["removed"] == w - u, "removed")
            check(r["removed_share"] == ((w - u) / w if w else None), "removed share")
    assignment = {p["package"]: p["phase"] for p in plan["packages"]}
    check(
        len(assignment) == 12
        and sum(v == "development" for v in assignment.values()) == 6,
        "assignment",
    )
    import hashlib

    ordered = sorted(assignment, key=lambda n: hashlib.sha256(n.encode()).hexdigest())
    check(
        all(
            assignment[n] == ("development" if i % 2 == 0 else "final")
            for i, n in enumerate(ordered)
        ),
        "hash split",
    )
    start = plan["start"] if phase == "development" else plan["final_start"]
    end = plan["development_end"] if phase == "development" else plan["end"]
    expected = con.execute(
        "select package,d from counts where d between ? and ? order by package,d",
        (start, end),
    ).fetchall()
    expected = [(p, d) for p, d in expected if assignment[p] == phase]
    check([(r["package"], r["date"]) for r in results] == expected, "phase origins")
    independent = []
    with localcontext() as ctx:
        ctx.prec = 80
        for r in results:
            p, d = r["package"], r["date"]
            w, u = con.execute(
                "select w,u from counts where package=? and d=?", (p, d)
            ).fetchone()
            history = con.execute(
                "select d,w,u from counts where package=? and d between date(?,'-28 days') and date(?,'-1 day') order by d",
                (p, d, d),
            ).fetchall()
            eligible = (
                w is not None
                and u is not None
                and len(history) == 28
                and all(a is not None and b is not None for _, a, b in history)
            )
            check((r["state"] == "scored") == eligible, "eligibility")
            if not eligible:
                continue
            check(
                r["history_start"] == history[0][0]
                and r["history_end"] == history[-1][0],
                "history boundary",
            )
            independent.append((p, d, {}))
            for view, current, past in [
                ("native", w, [a for _, a, b in history]),
                ("filtered", u, [b for _, a, b in history]),
                ("current_only", u, [a for _, a, b in history]),
            ]:
                z = decscore(current, past)
                check(
                    abs(Decimal(str(r[view + "_score"])) - z) <= Decimal("1e-10"),
                    (p, d, view, "score"),
                )
                fl = {str(k): z > k for k in plan["thresholds"]}
                for k in fl:
                    check(r[view + "_flags"][k] is bool(fl[k]), (p, d, view, k))
                independent[-1][2][view] = fl
            check(
                r["current_only_score"] <= r["native_score"] + 1e-12,
                "monotone same baseline",
            )

    def tally(items, k):
        n = sum(x[2]["native"][k] for x in items)
        f = sum(x[2]["filtered"][k] for x in items)
        c = sum(x[2]["current_only"][k] for x in items)
        both = sum(x[2]["native"][k] and x[2]["filtered"][k] for x in items)
        changed = n + f - 2 * both
        return dict(
            both=both,
            native_only=n - both,
            filtered_only=f - both,
            neither=len(items) - n - f + both,
            native=n,
            filtered=f,
            current_only=c,
            changed=changed,
            changed_fraction=changed / len(items) if items else None,
        )

    def check_group(observed, items):
        check(observed["scorable"] == len(items), "group denominator")
        for k in map(str, plan["thresholds"]):
            check(observed["thresholds"][k] == tally(items, k), "independent counts")

    check_group(summary, independent)
    for p, group in summary["by_package"].items():
        check_group(group, [x for x in independent if x[0] == p])
        check(group["scorable"] >= 30, "minimum per package")
    check(
        summary["expected_origins"] == len(expected)
        and summary["unknown_origins"] == len(expected) - len(independent),
        "unknown count",
    )
    for k in map(str, plan["thresholds"]):
        check(
            summary["equal_package_change_fraction"][k]
            == sum(
                tally([x for x in independent if x[0] == p], k)["changed_fraction"]
                for p in summary["by_package"]
            )
            / 6,
            "macro rate",
        )
    ranked = sorted(
        [r for r in results if r["state"] == "scored"],
        key=lambda r: (
            -abs(r["native_score"] - r["filtered_score"]),
            r["package"],
            r["date"],
        ),
    )[:10]
    check(
        [(r["package"], r["date"]) for r in ranked]
        == [(r["package"], r["date"]) for r in summary["largest_score_changes"]],
        "deterministic examples",
    )
    return dict(
        status="PASS_INDEPENDENT_SQLITE_DECIMAL",
        phase=phase,
        conditions=checked,
        scorable=len(independent),
        decimal_precision=80,
        absolute_score_tolerance=1e-10,
        exact_flags=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["development", "final"])
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    value = verify(Path(__file__).resolve().parents[1], a.phase)
    if a.output:
        a.output.write_bytes((json.dumps(value, indent=2) + "\n").encode())
    print(json.dumps(value))
