# Copyright 2026 Ooi Pin Jun
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Render derived PRISMA 2020 counts for new database/register reviews."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import sys
import textwrap
from typing import Any, Iterable

from assurance_chain import verify_derived_prisma


FORMATS = ("mermaid", "svg", "text")


def _breakdown(document: dict[str, Any], name: str, label: str,
               total: int, identity: str) -> list[tuple[str, int]] | None:
    if name not in document:
        return None
    entries = document[name]
    if not isinstance(entries, list):
        raise ValueError(f"{name} must be an array")
    result = []
    for index, entry in enumerate(entries):
        where = f"{name}[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where} must be an object")
        value = entry.get(label)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{where}.{label} must be a non-empty string")
        # XML 1.0 cannot represent these characters, even as entities.
        if any(not (c in "\t\n\r" or 0x20 <= ord(c) <= 0xD7FF
                       or 0xE000 <= ord(c) <= 0xFFFD
                       or 0x10000 <= ord(c) <= 0x10FFFF) for c in value):
            raise ValueError(f"{where}.{label} contains an invalid XML character")
        count = entry.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"{where}.count must be a non-negative integer")
        result.append((" ".join(value.split()), count))
    if sum(count for _, count in result) != total:
        raise ValueError(f"PRISMA sum({name}.count) != {identity} ({total})")
    return result


def _rows(document: Any) -> list[tuple[str, list[str], list[str] | None]]:
    if not isinstance(document, dict):
        raise ValueError("input must be an object containing flow_counts")
    block = document.get("flow_counts")
    if isinstance(block, dict) and not isinstance(block.get("sources", []), list):
        raise ValueError("flow_counts.sources must be an array")
    # The shared verifier owns all flow arithmetic and provenance validation.
    counts = verify_derived_prisma(block)
    sources = _breakdown(document, "records_by_source", "source",
                         counts["records_identified"], "records_identified")
    reasons = _breakdown(document, "reports_excluded_reasons", "reason",
                         counts["reports_excluded"], "reports_excluded")

    def label(text: str, key: str) -> str:
        return f"{text} (n = {counts[key]})"

    identified = ["Records identified from:",
                  label("Databases and registers", "records_identified")]
    if sources:
        identified.extend([
            f"{source} (n = {count})" for source, count in sources
        ])
    removed = ["Records removed before screening:",
               label("Duplicate records removed", "duplicates_removed")]
    if counts["records_removed_other_reasons"]:
        removed.append(label("Records removed for other reasons",
                             "records_removed_other_reasons"))
    excluded = [label("Reports excluded:", "reports_excluded")]
    if reasons:
        excluded.extend(f"{reason} (n = {count})" for reason, count in reasons)
    return [
        ("Identification", identified, removed),
        ("Screening", [label("Records screened", "records_screened")],
         [label("Records excluded", "records_excluded")]),
        ("Screening", [label("Reports sought for retrieval", "reports_sought")],
         [label("Reports not retrieved", "reports_not_retrieved")]),
        ("Screening", [label("Reports assessed for eligibility", "reports_assessed")],
         excluded),
        ("Included", [label("Studies included in review", "studies_included"),
                      label("Reports of included studies", "reports_included")], None),
    ]


def _mermaid_text(value: str) -> str:
    # Mermaid uses #decimal; entities. Encode syntax and HTML metacharacters
    # in supplied labels before adding our own line-break markup.
    return "".join(c if c.isalnum() or c in " .,:()-=" else f"#{ord(c)};"
                   for c in value)


def _mermaid(rows: list) -> str:
    lines = ["flowchart TB"]
    for phase in ("Identification", "Screening", "Included"):
        lines.append(f'  subgraph {phase.lower()}["{phase}"]')
        for index, (row_phase, left, right) in enumerate(rows):
            if row_phase != phase:
                continue
            for side, label in (("L", left), ("R", right)):
                if label is not None:
                    value = "<br/>".join(_mermaid_text(part) for part in label)
                    lines.append(f'    {side}{index}["{value}"]')
        lines.append("  end")
    for index, (_, _, right) in enumerate(rows):
        if index:
            lines.append(f"  L{index - 1} --> L{index}")
        if right is not None:
            lines.append(f"  L{index} --> R{index}")
    return "\n".join(lines) + "\n"


def _svg(rows: list) -> str:
    layout = []
    y = 50
    for phase, left, right in rows:
        wrapped = [[line for part in label for line in textwrap.wrap(part, 46)]
                   if label is not None else None for label in (left, right)]
        height = max(140 if phase == "Identification" else 80,
                     max(len(label or []) for label in wrapped) * 20 + 32)
        layout.append((phase, y, height, *wrapped))
        y += height + 48
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{y}" '
        f'viewBox="0 0 1100 {y}" role="img" aria-labelledby="title description">',
        '<title id="title">PRISMA 2020 flow diagram</title>',
        '<desc id="description">Identification, screening, and inclusion of studies '
        'in a new systematic review.</desc>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#222"/></marker></defs>',
        f'<rect width="1100" height="{y}" fill="white"/>',
    ]
    for phase in ("Identification", "Screening", "Included"):
        group = [row for row in layout if row[0] == phase]
        top = group[0][1]
        bottom = group[-1][1] + group[-1][2]
        middle = (top + bottom) / 2
        lines.extend([
            f'<rect x="10" y="{top}" width="100" height="{bottom - top}" '
            'fill="#eef2f5" stroke="#222"/>',
            f'<text x="60" y="{middle}" text-anchor="middle" '
            f'font-family="sans-serif" font-size="16" '
            f'transform="rotate(-90 60 {middle})">{phase}</text>',
        ])
    for index, (_, top, height, left, right) in enumerate(layout):
        for x, label in ((140, left), (660, right)):
            if label is None:
                continue
            lines.append(f'<rect x="{x}" y="{top}" width="420" height="{height}" '
                         'fill="white" stroke="#222"/>')
            for number, line in enumerate(label):
                lines.append(f'<text x="{x + 16}" y="{top + 27 + number * 20}" '
                             'font-family="monospace" font-size="14">'
                             f'{escape(line)}</text>')
        if right is not None:
            middle = top + height / 2
            lines.append(f'<path d="M 560 {middle} H 660" fill="none" '
                         'stroke="#222" marker-end="url(#arrow)"/>')
        if index:
            previous = layout[index - 1]
            start = previous[1] + previous[2]
            lines.append(f'<path d="M 350 {start} V {top}" fill="none" '
                         'stroke="#222" marker-end="url(#arrow)"/>')
    lines.append('</svg>')
    return "\n".join(lines) + "\n"


def render(document: Any, format: str = "mermaid") -> str:
    """Validate the derived block and optional breakdowns before rendering."""
    if format not in FORMATS:
        raise ValueError(f"unsupported format: {format}")
    rows = _rows(document)
    if format == "mermaid":
        return _mermaid(rows)
    if format == "svg":
        return _svg(rows)
    lines = []
    previous = None
    for phase, left, right in rows:
        if phase != previous:
            if lines:
                lines.append("")
            lines.append(phase)
            previous = phase
        lines.extend(left)
        lines.extend(right or [])
    return "\n".join(lines) + "\n"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON containing flow_counts and optional breakdowns")
    parser.add_argument("--format", choices=FORMATS, default="mermaid")
    parser.add_argument("--output", type=Path, help="write UTF-8 to PATH instead of stdout")
    args = parser.parse_args(argv)
    try:
        document = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result = render(document, args.format)
        if args.output is None:
            sys.stdout.write(result)
        else:
            args.output.write_text(result, encoding="utf-8")
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
