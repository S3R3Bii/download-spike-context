"""Evaluate one fixed phase from saved aggregates."""

import argparse, json
from pathlib import Path
from downloads import phase_scores, summarize


def main(phase, output=None):
    root = Path(__file__).resolve().parents[1]
    if phase == "final":
        from freeze_proof import verify

        verify(root)
    plan = json.loads((root / "data/source_plan.json").read_text())
    rows = json.loads((root / "data/paired_counts.json").read_text())
    scores = phase_scores(rows, plan, phase)
    summary = summarize(scores, plan)
    target = Path(output) if output else root / "results" / phase
    target.mkdir(parents=True, exist_ok=True)
    for name, obj in [("scores", scores), ("summary", summary)]:
        (target / (name + ".json")).write_bytes(
            (json.dumps(obj, indent=2, allow_nan=False) + "\n").encode()
        )
    print(
        json.dumps(
            dict(
                phase=phase,
                scorable=summary["scorable"],
                unknown=summary["unknown_origins"],
                thresholds=summary["thresholds"],
            )
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["development", "final"])
    p.add_argument("--output")
    a = p.parse_args()
    main(a.phase, a.output)
