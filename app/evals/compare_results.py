# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

import re
import sys
from pathlib import Path


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

    for name, score in new.items():
        change = score - old[name]
        lines.append(
            f"| {name} | {old[name]:.3f} | {score:.3f} | "
            f"{indicator(change)} {change:.3f} |"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    print(compare_results(Path(sys.argv[1]), Path(sys.argv[2])))
