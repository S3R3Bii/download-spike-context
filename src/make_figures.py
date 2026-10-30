"""Three source-bound views of traffic accounting and unchanged flags."""

import hashlib, json, shutil
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "svg.fonttype": "none",
        "path.simplify": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "text.color": "#203d4c",
        "axes.labelcolor": "#203d4c",
        "savefig.facecolor": "white",
    }
)


def read(n):
    return json.loads((ROOT / n).read_text())


def finish(fig, ax, name, items):
    ax.patch.set_gid("data-area")
    for item in items:
        item.pop("artist").set_gid(item["id"])
    hashes = {}
    for ext in ["pdf", "png", "svg"]:
        p = ROOT / "figures" / (name + "." + ext)
        fig.savefig(p, dpi=150, metadata={"Date": None} if ext == "svg" else None)
        if ext == "svg":
            p.write_bytes(
                (
                    "\n".join(x.rstrip() for x in p.read_text().splitlines()) + "\n"
                ).encode()
            )
        hashes[p.relative_to(ROOT).as_posix()] = hashlib.sha256(
            p.read_bytes()
        ).hexdigest()
    shutil.copyfile(
        ROOT / "figures" / (name + ".pdf"), ROOT / "paper/images" / (name + ".pdf")
    )
    result = dict(
        figure=name,
        axes=dict(xlim=list(ax.get_xlim()), ylim=list(ax.get_ylim())),
        items=items,
        files=hashes,
    )
    plt.close(fig)
    return result


def main():
    (ROOT / "paper/images").mkdir(parents=True, exist_ok=True)
    counts = read("data/paired_counts.json")
    scores = read("results/final/scores.json")
    summary = read("results/final/summary.json")
    maps = []
    fig, ax = plt.subplots(figsize=(8.8, 4.7))
    fig.subplots_adjust(left=0.10, right=0.97, bottom=0.20, top=0.72)
    items = []
    for j, k in enumerate([3, 6, 9]):
        for i, view in enumerate(["native", "filtered"]):
            value = summary["thresholds"][str(k)][view]
            x = j + [-0.17, 0.17][i]
            width = 0.29
            artist = ax.bar(
                x,
                value,
                width,
                color=["#255d74", "#b36028"][i],
                label=["Native total", "Publisher filtered"][i] if j == 0 else None,
            )[0]
            ax.text(x, value + 0.10, str(value), ha="center", fontsize=10)
            items.append(
                dict(
                    artist=artist,
                    id=f"flags-{view}-{k}",
                    kind="flags",
                    view=view,
                    threshold=k,
                    x=x,
                    width=width,
                    value=value,
                    display=str(value),
                )
            )
    ax.set(
        xticks=range(3),
        xticklabels=["3 (sensitivity)", "6 (primary)", "9 (sensitivity)"],
        xlim=(-0.6, 2.6),
        ylim=(0, 5.2),
        ylabel="Flagged package-days out of 360",
        xlabel="Fixed one-sided score threshold: strict score > k",
    )
    ax.legend(frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.17))
    ax.yaxis.grid(alpha=0.18)
    ax.set_axisbelow(True)
    fig.suptitle(
        "No flag changes in the final comparison",
        x=0.10,
        y=0.97,
        ha="left",
        weight="bold",
        fontsize=16,
    )
    fig.text(
        0.10,
        0.87,
        "Six other packages, 30 Aug–28 Oct 2026. All four k=3 flags are the same Flask dates.",
        fontsize=10,
    )
    maps.append(finish(fig, ax, "final_flags", items))
    packages = sorted({r["package"] for r in counts})
    fig, ax = plt.subplots(figsize=(8.8, 6.0))
    fig.subplots_adjust(left=0.16, right=0.95, bottom=0.14, top=0.79)
    items = []
    for i, p in enumerate(packages):
        selected = [r for r in counts if r["package"] == p]
        w = sum(r["with_mirrors"] for r in selected)
        u = sum(r["without_mirrors"] for r in selected)
        value = 100 * (w - u) / w
        y = len(packages) - 1 - i
        artist = ax.barh(y, value, 0.63, color="#255d74")[0]
        display = f"{value:.2f}%"
        ax.text(value + 0.12, y, display, va="center", fontsize=9)
        items.append(
            dict(
                artist=artist,
                id="removed-" + p,
                kind="removed",
                package=p,
                y=y,
                height=0.63,
                value=value,
                display=display,
                with_sum=w,
                without_sum=u,
            )
        )
    ax.set(
        yticks=range(len(packages)),
        yticklabels=list(reversed(packages)),
        xlim=(0, 2.3),
        ylim=(-0.7, len(packages) - 0.3),
        xlabel="Publisher-filter-removed share of each package total (%)",
    )
    ax.xaxis.grid(alpha=0.18)
    ax.set_axisbelow(True)
    fig.suptitle(
        "The filter removes traffic, not identified users",
        x=0.16,
        y=0.97,
        ha="left",
        weight="bold",
        fontsize=16,
    )
    fig.text(
        0.16,
        0.88,
        "Fixed 150-date context: 1 Jun–28 Oct 2026. Weighted ratio within each package.",
        fontsize=10,
    )
    fig.text(
        0.16,
        0.035,
        "Inspected SQL also excludes unknown installers; CI/CD remains. No all-bot or adoption measure.",
        fontsize=9,
    )
    maps.append(finish(fig, ax, "filter_accounting", items))
    fig, ax = plt.subplots(figsize=(8.8, 5.5))
    fig.subplots_adjust(left=0.12, right=0.96, bottom=0.18, top=0.79)
    items = []
    for i, r in enumerate(scores):
        x = r["native_score"]
        y = r["filtered_score"]
        artist = ax.plot(
            [x], [y], marker="o", ms=3.5, ls="None", color="#255d74", alpha=0.5
        )[0]
        items.append(
            dict(
                artist=artist,
                id="score-" + str(i),
                kind="score",
                package=r["package"],
                date=r["date"],
                x=x,
                value=y,
            )
        )
    ax.plot([-10, 6], [-10, 6], color="#788893", ls="--", lw=1, label="Same score")
    ax.axhline(3, color="#b36028", lw=0.8, ls=":")
    ax.axvline(3, color="#b36028", lw=0.8, ls=":")
    ax.set(
        xlim=(-10, 6),
        ylim=(-10, 6),
        xlabel="Native score (log-count difference / guarded MAD)",
        ylabel="Publisher-filtered score (same units)",
    )
    ax.legend(frameon=False, loc="lower right")
    ax.grid(alpha=0.13)
    ax.set_axisbelow(True)
    fig.suptitle(
        "Both baselines matter", x=0.12, y=0.97, ha="left", weight="bold", fontsize=16
    )
    fig.text(
        0.12,
        0.88,
        "360 final package-days; each point uses its own prior 28 consecutive paired dates.",
        fontsize=10,
    )
    fig.text(
        0.12,
        0.045,
        "Dotted lines show k=3. The primary k=6 and sensitivity k=9 produce no flags.",
        fontsize=9,
    )
    maps.append(finish(fig, ax, "paired_scores", items))
    (ROOT / "figures/value_map.json").write_bytes(
        (json.dumps(maps, indent=2) + "\n").encode()
    )
    print(json.dumps(dict(figures=3, mapped_items=sum(len(x["items"]) for x in maps))))


if __name__ == "__main__":
    main()
