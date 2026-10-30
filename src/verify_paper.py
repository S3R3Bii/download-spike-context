"""Check measured displays, extracted pages and retained build identities."""

import ast, hashlib, json, re
from datetime import datetime
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def read(n):
    return json.loads((ROOT / n).read_text())


def main():
    tex = (ROOT / "paper/main.tex").read_text()
    bindings = read("paper_bindings.json")
    pdf = PdfReader(ROOT / "paper/manuscript.pdf")
    assert len(pdf.pages) == 6
    pages = [p.extract_text() or "" for p in pdf.pages]
    assert all(len(p) > 1500 for p in pages)
    flat = "\n".join(pages)
    checks = 0
    for name, item in bindings.items():
        path = (ROOT / item["file"]).resolve()
        assert path.is_relative_to(ROOT) and path.suffix == ".json"
        value = json.loads(path.read_text())
        for key in item["pointer"]:
            value = value[key]
        assert value == item["value"]
        checks += 1
        assert item["display"] == str(value)
        checks += 1
        assert "\\newcommand{\\" + name + "}{" + item["display"] + "}" in tex
        checks += 1
        assert tex.count("\\" + name) >= 2 and item["display"] in flat
        checks += 1
    assert len(bindings) == 61
    checks += 1
    source = read("data/source_receipts.json")
    assert len(source) == 12 and all(r["status"] == 200 for r in source)
    assert (
        sum(r["bytes"] for r in source)
        == read("data/source_verification.json")["source_bytes"]
    )
    checks += 2
    starts = [datetime.fromisoformat(r["start_utc"]) for r in source]
    assert min((b - a).total_seconds() for a, b in zip(starts, starts[1:])) >= 10
    checks += 1
    assert (
        starts[0].strftime("%H:%M:%S") == "21:55:41"
        and datetime.fromisoformat(source[-1]["end_utc"]).strftime("%H:%M:%S")
        == "21:57:31"
    )
    checks += 1
    assert (
        len(read("data/dependency_freeze.json")["files"]) == 29
        and "29 dependencies" in tex
    )
    checks += 1
    fixture_count = sum(
        isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        for p in (ROOT / "tests").glob("test_*.py")
        for n in ast.walk(ast.parse(p.read_text()))
    )
    assert fixture_count == 21 and "Twenty-one fixture methods" in tex
    checks += 1
    final = read("results/final/scores.json")
    flagged = {(r["package"], r["date"]) for r in final if r["native_flags"]["3"]}
    assert flagged == {
        ("flask", d) for d in ["2026-09-30", "2026-10-01", "2026-10-27", "2026-10-28"]
    }
    checks += 1
    assert all(
        r["native_flags"] == r["filtered_flags"] == r["current_only_flags"]
        for r in final
    )
    checks += 1
    assert not any(
        r[v + "_flags"][str(k)]
        for r in final
        for v in ["native", "filtered", "current_only"]
        for k in [6, 9]
    )
    checks += 1
    for phrase in [
        "80-digit Decimal",
        "10^{-10}",
        "not peer reviewed",
        "no observed alert reduction",
        "not blinded collection",
        "authored illustrative settings",
        "Inspected commit:",
        "SOURCE_REVISION_CLARIFICATION",
    ]:
        where = (
            (ROOT / "SOURCE_REVISION_CLARIFICATION.md").read_text()
            if phrase == "SOURCE_REVISION_CLARIFICATION"
            else tex
        )
        if phrase == "SOURCE_REVISION_CLARIFICATION":
            assert (ROOT / (phrase + ".md")).exists()
        else:
            assert phrase in where, phrase
        checks += 1
    assert (
        "tree/commit label" in tex
        and "35203633e2a57a58ec0e767a54058ed01a50a9fc"
        in (ROOT / "SOURCE_REVISION_CLARIFICATION.md").read_text()
    )
    checks += 1
    build = read("paper/build_receipt.json")
    assert (
        build["status"] == "PASS_COMPILE_AND_SIX_PAGE_VISUAL_REVIEW"
        and build["pages"] == 6
        and not build["layout_warnings"]
    )
    checks += 1
    for path, digest in build["artifact_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
        checks += 1
    for p in (ROOT / "paper/images").glob("*.pdf"):
        assert p.read_bytes() == (ROOT / "figures" / p.name).read_bytes()
        checks += 1
    receipt = dict(
        status="PASS_SOURCE_BOUND_MANUSCRIPT",
        pages=6,
        bound_measurements=len(bindings),
        conditions=checks,
        manuscript_sha256=hashlib.sha256(
            (ROOT / "paper/manuscript.pdf").read_bytes()
        ).hexdigest(),
        page_characters=[len(p) for p in pages],
        source_correction_explicit=True,
        rendering="Recorded local Poppler visual review; CI checks identities and extracted text without compiling TeX.",
    )
    (ROOT / "paper_verification.json").write_bytes(
        (json.dumps(receipt, indent=2) + "\n").encode()
    )
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
