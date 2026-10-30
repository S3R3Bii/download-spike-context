import json, math, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from downloads import parse, project, assess, flags, anomaly, strict_json
from acquire import allowed


class DownloadTests(unittest.TestCase):
    def raw(self, rows, package="example"):
        return json.dumps(dict(package=package, type="overall_downloads", data=rows))

    def cells(self, w=100, u=50):
        return [
            dict(date="2026-06-01", category="with_mirrors", downloads=w),
            dict(date="2026-06-01", category="without_mirrors", downloads=u),
        ]

    def test_nested_not_disjoint(self):
        c = parse(self.raw(self.cells()), "example")
        r = project(c, "example", dict(start="2026-06-01", end="2026-06-01"))[0]
        self.assertEqual((r["removed"], r["removed_share"]), (50, 0.5))

    def test_zero_share_unknown(self):
        c = parse(self.raw(self.cells(0, 0)), "example")
        self.assertIsNone(
            project(c, "example", dict(start="2026-06-01", end="2026-06-01"))[0][
                "removed_share"
            ]
        )

    def test_boolean_and_negative_rejected(self):
        for n in [True, -1, 1.5, "3"]:
            with self.assertRaises(ValueError):
                parse(self.raw(self.cells(n, 0)), "example")

    def test_unknown_category(self):
        rows = self.cells()
        rows[0]["category"] = "all"
        with self.assertRaises(ValueError):
            parse(self.raw(rows), "example")

    def test_duplicate_cells_even_equal(self):
        with self.assertRaises(ValueError):
            parse(self.raw(self.cells() + self.cells()[:1]), "example")

    def test_duplicate_json_keys(self):
        with self.assertRaises(ValueError):
            strict_json('{"package":"x","package":"x"}')

    def test_identity(self):
        with self.assertRaises(ValueError):
            parse(self.raw(self.cells()), "other")

    def test_invalid_dates(self):
        rows = self.cells()
        rows[0]["date"] = "2026-02-30"
        with self.assertRaises(ValueError):
            parse(self.raw(rows), "example")

    def test_nested_violation(self):
        with self.assertRaises(ValueError):
            parse(self.raw(self.cells(1, 2)), "example")

    def test_missing_not_zero(self):
        c = parse(self.raw(self.cells()[:1]), "example")
        r = project(c, "example", dict(start="2026-06-01", end="2026-06-02"))
        self.assertTrue(
            all(x["state"] == "missing_pair" and x["removed"] is None for x in r)
        )

    def test_constant_floor(self):
        self.assertAlmostEqual(anomaly(100, [100] * 28), 0)
        self.assertAlmostEqual(
            anomaly(1000, [100] * 28), (math.log1p(1000) - math.log1p(100)) / 0.1
        )

    def test_strict_threshold(self):
        self.assertFalse(flags(6, [6])["6"])
        self.assertTrue(flags(math.nextafter(6, math.inf), [6])["6"])

    def test_spike_clears(self):
        r = assess(1000, 100, [100] * 28, [100] * 28)
        self.assertGreater(r["native_score"], 6)
        self.assertEqual(r["filtered_score"], 0)

    def test_spike_appears_after_baseline_change(self):
        r = assess(1000, 100, [10000] * 28, [10] * 28)
        self.assertLess(r["native_score"], 6)
        self.assertGreater(r["filtered_score"], 6)

    def test_unknown_history(self):
        for w, u in [([1] * 27, [1] * 27), ([None] * 28, [1] * 28)]:
            self.assertEqual(
                assess(1, 1, w, u)["state"], "UNKNOWN_INCOMPLETE_PAIRED_HISTORY"
            )

    def test_nested_history_rejected(self):
        with self.assertRaises(ValueError):
            assess(1, 1, [1] * 28, [2] * 28)

    def test_current_only_monotonic(self):
        r = assess(1000, 10, list(range(50, 78)), list(range(10, 38)))
        self.assertLessEqual(r["current_only_score"], r["native_score"])

    def test_large_integer_finite(self):
        self.assertTrue(math.isfinite(anomaly(10**100, [10**99] * 28)))

    def test_redirect_guard(self):
        u = "https://pypistats.org/api/packages/example/overall"
        self.assertTrue(allowed(u + "/", u))
        for bad in [
            u + "?mirrors=true",
            u.replace("https:", "http:"),
            u.replace("pypistats.org", "evil.example"),
            u + "/extra",
            u + "#x",
        ]:
            self.assertFalse(allowed(bad, u))


if __name__ == "__main__":
    unittest.main()
