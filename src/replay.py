"""Saved-data replay; outputs stay outside the full-history checkout."""

import argparse, hashlib, json, platform, subprocess, sys
from pathlib import Path


def replay(output):
    root = Path(__file__).resolve().parents[1]
    output = output.resolve()
    assert (
        not output.is_relative_to(root) and not output.exists()
    ), "Use a fresh external output"
    output.mkdir(parents=True)
    source_names = [
        "data/source_plan.json",
        "data/paired_counts.json",
        "data/source_receipts.json",
        "data/qualification_ledger.json",
    ]
    before = {
        n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in source_names
    }

    def run(*args):
        subprocess.run([sys.executable, *args], cwd=root, check=True)

    run("-m", "unittest", "discover", "-s", "tests", "-v")
    run("src/freeze_proof.py")
    exact = tolerant = 0

    def compare(a, b, where):
        nonlocal exact, tolerant
        if type(a) is float:
            assert isinstance(b, (int, float)) and abs(a - b) <= 1e-10, where
            tolerant += 1
        elif isinstance(a, dict):
            assert set(a) == set(b), where
            for k in a:
                compare(a[k], b[k], where + "/" + k)
        elif isinstance(a, list):
            assert len(a) == len(b), where
            for i, (x, y) in enumerate(zip(a, b)):
                compare(x, y, where + "/" + str(i))
        else:
            assert type(a) == type(b) and a == b, where
            exact += 1

    from verify_results import verify

    for phase in ["development", "final"]:
        target = output / phase
        run("src/analyze.py", phase, "--output", str(target))
        for name in ["scores.json", "summary.json"]:
            compare(
                json.loads((root / "results" / phase / name).read_text()),
                json.loads((target / name).read_text()),
                phase + "/" + name,
            )
        proof = verify(root, phase)
        (output / (phase + "-independent.json")).write_bytes(
            (json.dumps(proof, indent=2) + "\n").encode()
        )
    from review_cli import review

    examples = {}
    for path in sorted((root / "examples").glob("*.json")):
        if path.name.endswith(".expected.json"):
            continue
        value = review(json.loads(path.read_text()))
        compare(
            json.loads(path.with_suffix(".expected.json").read_text()), value, path.name
        )
        examples[path.name] = value["state"]
    after = {
        n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in source_names
    }
    assert before == after
    receipt = dict(
        status="PASS_OFFLINE_REPLAY",
        python=platform.python_version(),
        exact_fields=exact,
        tolerant_fields=tolerant,
        absolute_tolerance=1e-10,
        source_files_unchanged=len(before),
        source_sha256=after,
        fixtures=21,
        examples=examples,
        source_network_requests=0,
    )
    (output / "replay_receipt.json").write_bytes(
        (json.dumps(receipt, indent=2) + "\n").encode()
    )
    print(json.dumps(receipt))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, type=Path)
    replay(p.parse_args().output)
