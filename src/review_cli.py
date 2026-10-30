"""Offline educational input only; no network or outgoing alerts."""

import argparse, json
from pathlib import Path
from downloads import assess, flags


def review(item):
    result = assess(
        item["with_current"],
        item["without_current"],
        item["with_history"],
        item["without_history"],
    )
    if result["state"] == "scored":
        for view in ["native", "filtered", "current_only"]:
            result[view + "_flags"] = flags(result[view + "_score"], (3, 6, 9))
    result["interpretation"] = (
        "Check counter definitions and release/deployment context; this does not label a true anomaly or adoption."
    )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    a = p.parse_args()
    print(json.dumps(review(json.loads(a.input.read_text())), indent=2))
