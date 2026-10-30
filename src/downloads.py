"""Transparent paired-counter accounting; fixed settings are in source_plan.json."""

import json, math
from datetime import date, timedelta
from statistics import median

CATEGORIES = ("with_mirrors", "without_mirrors")


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def valid_count(n):
    if type(n) is not int or n < 0:
        raise ValueError("count must be a nonnegative integer")
    return n


def day(text):
    d = date.fromisoformat(text)
    if d.isoformat() != text:
        raise ValueError("noncanonical date")
    return d


def parse(raw, package):
    body = strict_json(raw)
    if body.get("package") != package or body.get("type") != "overall_downloads":
        raise ValueError("source identity")
    cells = {}
    for r in body["data"]:
        category = r["category"]
        d = day(r["date"])
        if category not in CATEGORIES:
            raise ValueError("unknown category")
        key = (d.isoformat(), category)
        if key in cells:
            raise ValueError("duplicate category/date")
        cells[key] = valid_count(r["downloads"])
    for d in {x[0] for x in cells}:
        w = cells.get((d, CATEGORIES[0]))
        u = cells.get((d, CATEGORIES[1]))
        if w is not None and u is not None and w < u:
            raise ValueError("filtered count exceeds nested total")
    return cells


def calendar(start, end):
    d = day(start)
    last = day(end)
    while d <= last:
        yield d.isoformat()
        d += timedelta(days=1)


def project(cells, package, plan):
    rows = []
    for d in calendar(plan["start"], plan["end"]):
        w = cells.get((d, CATEGORIES[0]))
        u = cells.get((d, CATEGORIES[1]))
        rows.append(
            dict(
                package=package,
                date=d,
                with_mirrors=w,
                without_mirrors=u,
                removed=None if w is None or u is None else w - u,
                removed_share=None if w in (None, 0) or u is None else (w - u) / w,
                state="paired" if w is not None and u is not None else "missing_pair",
            )
        )
    return rows


def anomaly(current, history, floor=0.1):
    valid_count(current)
    if len(history) != 28 or any(x is None for x in history):
        return None
    for x in history:
        valid_count(x)
    logs = [math.log1p(x) for x in history]
    center = median(logs)
    mad = median([abs(x - center) for x in logs])
    return (math.log1p(current) - center) / max(mad, floor)


def flags(score, thresholds):
    return {str(k): None if score is None else score > k for k in thresholds}


def assess(
    with_current, without_current, with_history, without_history, thresholds=(3, 6, 9)
):
    valid_count(with_current)
    valid_count(without_current)
    if without_current > with_current:
        raise ValueError("nested counter")
    if len(with_history) != len(without_history):
        raise ValueError("paired history length")
    for w, u in zip(with_history, without_history):
        if w is not None:
            valid_count(w)
        if u is not None:
            valid_count(u)
        if w is not None and u is not None and w < u:
            raise ValueError("nested history counter")
    if len(with_history) != 28 or any(
        x is None for x in with_history + without_history
    ):
        return dict(
            state="UNKNOWN_INCOMPLETE_PAIRED_HISTORY",
            native_score=None,
            filtered_score=None,
            current_only_score=None,
        )
    return dict(
        state="scored",
        native_score=anomaly(with_current, with_history),
        filtered_score=anomaly(without_current, without_history),
        current_only_score=anomaly(without_current, with_history),
    )


def phase_scores(rows, plan, phase):
    assignment = {r["package"]: r["phase"] for r in plan["packages"]}
    keyed = {(r["package"], r["date"]): r for r in rows}
    out = []
    first = plan["start"] if phase == "development" else plan["final_start"]
    last = plan["development_end"] if phase == "development" else plan["end"]
    for package in sorted(p for p, v in assignment.items() if v == phase):
        for d in calendar(first, last):
            row = keyed[(package, d)]
            origin = day(d)
            prior = [
                keyed.get((package, (origin - timedelta(days=i)).isoformat()))
                for i in range(28, 0, -1)
            ]
            if row["state"] != "paired" or any(
                p is None or p["state"] != "paired" for p in prior
            ):
                out.append(
                    dict(
                        package=package,
                        date=d,
                        state="UNKNOWN_INCOMPLETE_PAIRED_HISTORY",
                    )
                )
                continue
            scores = assess(
                row["with_mirrors"],
                row["without_mirrors"],
                [p["with_mirrors"] for p in prior],
                [p["without_mirrors"] for p in prior],
            )
            for view in ["native", "filtered", "current_only"]:
                scores[view + "_flags"] = flags(
                    scores[view + "_score"], plan["thresholds"]
                )
            out.append(
                dict(
                    package=package,
                    date=d,
                    history_start=(origin - timedelta(days=28)).isoformat(),
                    history_end=(origin - timedelta(days=1)).isoformat(),
                    **scores
                )
            )
    counts = {
        p: sum(x["state"] == "scored" for x in out if x["package"] == p)
        for p in assignment
        if assignment[p] == phase
    }
    if any(v < plan["minimum_scorable_per_package"] for v in counts.values()):
        raise ValueError("scorable coverage gate")
    return out


def summarize(scores, plan):
    scored = [r for r in scores if r["state"] == "scored"]

    def group(rows):
        result = dict(scorable=len(rows), thresholds={})
        for k in map(str, plan["thresholds"]):
            counts = {
                name: 0
                for name in [
                    "both",
                    "native_only",
                    "filtered_only",
                    "neither",
                    "native",
                    "filtered",
                    "current_only",
                ]
            }
            for r in rows:
                n = r["native_flags"][k]
                f = r["filtered_flags"][k]
                c = r["current_only_flags"][k]
                counts[
                    (
                        "both"
                        if n and f
                        else "native_only" if n else "filtered_only" if f else "neither"
                    )
                ] += 1
                for name, v in [("native", n), ("filtered", f), ("current_only", c)]:
                    counts[name] += int(v)
            counts["changed"] = counts["native_only"] + counts["filtered_only"]
            counts["changed_fraction"] = counts["changed"] / len(rows) if rows else None
            result["thresholds"][k] = counts
        return result

    by = {
        p: group([r for r in scored if r["package"] == p])
        for p in sorted({r["package"] for r in scores})
    }
    result = group(scored)
    result.update(
        expected_origins=len(scores),
        unknown_origins=len(scores) - len(scored),
        by_package=by,
    )
    result["equal_package_change_fraction"] = {
        str(k): sum(v["thresholds"][str(k)]["changed_fraction"] for v in by.values())
        / len(by)
        for k in plan["thresholds"]
    }
    result["largest_score_changes"] = [
        dict(
            package=r["package"],
            date=r["date"],
            native_score=r["native_score"],
            filtered_score=r["filtered_score"],
            difference=r["native_score"] - r["filtered_score"],
        )
        for r in sorted(
            scored,
            key=lambda r: (
                -abs(r["native_score"] - r["filtered_score"]),
                r["package"],
                r["date"],
            ),
        )[:10]
    ]
    return result
