# Inspect both directions before deciding what to review

A download alert depends on today's count and its historical baseline. This local exercise accepts paired integer counters and prints the fixed scores and flags. The examples are authored, not measured incidents.

~~~sh
python src/review_cli.py examples/removed-current-spike.json
python src/review_cli.py examples/revealed-filtered-spike.json
python src/review_cli.py examples/unknown-short-history.json
~~~

The first example keeps both 28-day histories at 100, then uses today's total 1,000 and filtered count 100. Its native spike clears after filtering. The second has total history 10,000 and filtered history 10, then today's total 1,000 and filtered count 100. Filtering lowers today's count while revealing an increase relative to the much smaller filtered baseline. The third stays UNKNOWN because three observations cannot fill 28 consecutive daily pairs.

Implementation tasks:
1. Trace the exact prior dates and show which count and baseline produce each view.
2. Explain why total plus filtered double-counts observations.
3. Reject negative, boolean or inverted nested counters. Keep missing days unknown.
4. Preserve all three authored thresholds and inspect flag changes in both directions.

The 28-day window, unscaled log-MAD, 0.1 floor and thresholds 3/6/9 are authored teaching settings, with no fitted or optimal threshold. The CLI makes no network request or outgoing alert. A changed flag asks for context; it is not a true anomaly, adoption measure, incident or production decision.
