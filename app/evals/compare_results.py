# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

import re
import sys
from pathlib import Path

METRICS = ("precision", "recall", "f1", "accuracy")


def extract_scores(path: Path) -> dict[str, float]:
    """Extract all scores in the markdown from the previous run."""
    text = path.read_text()
    return {
        name: float(score) for name, score in re.findall(r"• (\w+): ([\d.]+)", text)
    }


def indicator(change: float) -> str:
    """Return an indicator for the change in score per run."""
    if change > 0:
        return "🟩"
    if change < 0:
        return "🔴"
    return "⬜"


def compare_results(previous: Path, current: Path) -> str:
    """Generates markdown that compared current scores with previous scores."""
    old = extract_scores(previous)
    new = extract_scores(current)

    lines = [
        "## Comparison with previous run",
        "",
        "| Field | Previous | Current | Change |",
        "|---|---:|---:|---:|",
    ]
    pooled: dict[str, dict[str, str]] = {}

    for name, score in new.items():
        field, _, metric = name.rpartition("_")
        if metric in METRICS:
            cell = f"{score:.3f}"
            if name in old:  # the first run after this change has no previous value
                change = score - old[name]
                cell += f" {indicator(change)} {change:+.3f}"
            pooled.setdefault(field.removeprefix("run_"), {})[metric] = cell
            continue
        change = score - old[name]
        lines.append(
            f"| {name} | {old[name]:.3f} | {score:.3f} | "
            f"{indicator(change)} {change:.3f} |"
        )

    lines += [
        "",
        "### Precision, recall and F1",
        "",
        "Pooled over all items; change from the previous run next to each value.",
        "",
        "| Field | " + " | ".join(METRICS) + " |",
        "|---|" + "---:|" * len(METRICS),
    ]
    for field, values in pooled.items():
        cells = " | ".join(values[m] for m in METRICS)
        lines.append(f"| {field} | {cells} |")

    return "\n".join(lines)


if __name__ == "__main__":
    print(compare_results(Path(sys.argv[1]), Path(sys.argv[2])))
