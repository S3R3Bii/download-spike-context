"""Check source values and actual SVG coordinates, including zero-height bars."""

import hashlib, json, re
from pathlib import Path
from xml.etree import ElementTree as E

ROOT = Path(__file__).resolve().parents[1]
S = "{http://www.w3.org/2000/svg}"


def read(n):
    return json.loads((ROOT / n).read_text())


def vertices(node):
    path = node.find(".//" + S + "path")
    assert path is not None
    values = [
        float(x)
        for x in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", path.attrib["d"])
    ]
    assert len(values) % 2 == 0
    return list(zip(values[::2], values[1::2]))


def main():
    rows = read("data/paired_counts.json")
    scores = read("results/final/scores.json")
    maps = read("figures/value_map.json")
    values = coordinates = hashes = 0
    assert len(maps) == 3
    for figure in maps:
        tree = E.parse(ROOT / "figures" / (figure["figure"] + ".svg"))
        ids = {n.get("id"): n for n in tree.iter() if n.get("id")}
        area = vertices(ids["data-area"])
        left = min(x for x, y in area)
        right = max(x for x, y in area)
        top = min(y for x, y in area)
        bottom = max(y for x, y in area)
        xmin, xmax = figure["axes"]["xlim"]
        ymin, ymax = figure["axes"]["ylim"]
        for item in figure["items"]:
            kind = item["kind"]
            if kind == "flags":
                value = sum(
                    r[item["view"] + "_score"] > item["threshold"] for r in scores
                )
                x = [3, 6, 9].index(item["threshold"]) + (
                    -0.17 if item["view"] == "native" else 0.17
                )
                assert (
                    item["x"] == x
                    and item["width"] == 0.29
                    and figure["axes"] == dict(xlim=[-0.6, 2.6], ylim=[0, 5.2])
                )
                expected = [
                    (x - 0.145, 0),
                    (x + 0.145, 0),
                    (x + 0.145, value),
                    (x - 0.145, value),
                ]
                assert item["display"] == str(value) and item["display"] in "".join(
                    tree.getroot().itertext()
                )
            elif kind == "removed":
                selected = [r for r in rows if r["package"] == item["package"]]
                w = sum(r["with_mirrors"] for r in selected)
                u = sum(r["without_mirrors"] for r in selected)
                value = 100 * (w - u) / w
                packages = sorted({r["package"] for r in rows})
                y = 11 - packages.index(item["package"])
                assert (
                    item["with_sum"] == w
                    and item["without_sum"] == u
                    and item["y"] == y
                    and item["height"] == 0.63
                )
                assert figure["axes"] == dict(xlim=[0, 2.3], ylim=[-0.7, 11.7])
                expected = [
                    (0, y - 0.315),
                    (value, y - 0.315),
                    (value, y + 0.315),
                    (0, y + 0.315),
                ]
                assert item["display"] == f"{value:.2f}%" and item[
                    "display"
                ] in "".join(tree.getroot().itertext())
            else:
                assert kind == "score" and figure["axes"] == dict(
                    xlim=[-10, 6], ylim=[-10, 6]
                )
                row = next(
                    r
                    for r in scores
                    if (r["package"], r["date"]) == (item["package"], item["date"])
                )
                value = row["filtered_score"]
                assert item["x"] == row["native_score"]
                expected = [(row["native_score"], value)]
            assert item["value"] == value
            values += 1
            projected = [
                (
                    left + (x - xmin) / (xmax - xmin) * (right - left),
                    bottom - (y - ymin) / (ymax - ymin) * (bottom - top),
                )
                for x, y in expected
            ]
            if kind == "score":
                use = ids[item["id"]].find(".//" + S + "use")
                assert use is not None
                actual = [(float(use.get("x")), float(use.get("y")))]
            else:
                actual = vertices(ids[item["id"]])
            assert len(actual) == len(projected), (item["id"], actual, projected)
            for (x, y), (a, b) in zip(actual, projected):
                assert abs(x - a) <= 3e-5 and abs(y - b) <= 3e-5, (
                    item["id"],
                    (x, y),
                    (a, b),
                )
                coordinates += 2
        for name, digest in figure["files"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
            hashes += 1
    result = dict(
        status="PASS_SOURCE_VALUES_AND_ACTUAL_SVG_GEOMETRY",
        figures=3,
        source_values=values,
        svg_coordinates=coordinates,
        file_hashes=hashes,
    )
    (ROOT / "figures/verification.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode()
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
