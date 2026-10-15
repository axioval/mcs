"""The engine's measured registry as MCS mirrors it.

`scripts/measured_registry.json` is a projection of the `measuredValues` and
`measuredMembers` of the engine's authoring catalogue
(`crates/engine/rules/tests/golden/catalogue.json` of axioval/engine): every
measured value and measured member list with its subject and parameters, the
grammar the engine's `measured::parse` and `measured::parse_members` check.
Labels, help, services and member fields are left out.

Regenerate it from an engine checkout, recording the engine commit:

    python3 scripts/measured_registry.py \\
      ../engine/crates/engine/rules/tests/golden/catalogue.json <commit>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SNAPSHOT = Path(__file__).with_name("measured_registry.json")
REPOSITORY = "https://github.com/axioval/engine"
SOURCE = "crates/engine/rules/tests/golden/catalogue.json"
# The parts of a parameter the grammar depends on, in the catalogue's order.
PARAMETER_FIELDS = ("key", "kind", "required", "default", "references")


def project_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """The name, subject and parameters of one catalogue entry."""
    projected: dict[str, Any] = {"name": entry["name"]}
    if "subject" in entry:
        projected["subject"] = entry["subject"]
    projected["parameters"] = [
        {field: parameter[field] for field in PARAMETER_FIELDS if field in parameter}
        for parameter in entry["parameters"]
    ]
    return projected


def project(catalogue: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The measured values and member lists of the engine's catalogue."""
    return {
        "measuredValues": [project_entry(entry) for entry in catalogue["measuredValues"]],
        "measuredMembers": [
            project_entry(entry) for entry in catalogue["measuredMembers"]
        ],
    }


def render(registry: dict[str, list[dict[str, Any]]], commit: str) -> str:
    """The snapshot's text: one parameter per line, deterministic."""

    def dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))

    lines = [
        "{",
        f'  "engine": {dump({"repository": REPOSITORY, "commit": commit, "source": SOURCE})},',
    ]
    for index, section in enumerate(("measuredValues", "measuredMembers")):
        lines.append(f'  "{section}": [')
        entries = registry[section]
        for position, entry in enumerate(entries):
            head = {key: value for key, value in entry.items() if key != "parameters"}
            opening = dump(head)[:-1]
            parameters = entry["parameters"]
            if parameters:
                lines.append(f'    {opening}, "parameters": [')
                for number, parameter in enumerate(parameters):
                    comma = "," if number + 1 < len(parameters) else ""
                    lines.append(f"      {dump(parameter)}{comma}")
                lines.append("    ]}" + ("," if position + 1 < len(entries) else ""))
            else:
                lines.append(
                    f'    {opening}, "parameters": []}}'
                    + ("," if position + 1 < len(entries) else "")
                )
        lines.append("  ]" + ("," if index == 0 else ""))
    lines.append("}")
    return "\n".join(lines) + "\n"


def load() -> dict[str, Any]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def drift(snapshot: dict[str, Any], catalogue: dict[str, Any]) -> list[str]:
    """How the engine's catalogue differs from the snapshot, one line per
    measured value or member list added, removed or changed."""
    upstream = project(catalogue)
    differences = []
    for section in ("measuredValues", "measuredMembers"):
        ours = {entry["name"]: entry for entry in snapshot[section]}
        theirs = {entry["name"]: entry for entry in upstream[section]}
        for name in sorted(theirs.keys() - ours.keys()):
            differences.append(f"{section}: the engine adds {name!r}")
        for name in sorted(ours.keys() - theirs.keys()):
            differences.append(f"{section}: the engine no longer has {name!r}")
        for name in sorted(ours.keys() & theirs.keys()):
            if ours[name] != theirs[name]:
                differences.append(f"{section}: the engine changes {name!r}")
    return differences


def main(arguments: list[str]) -> int:
    if len(arguments) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    catalogue = json.loads(Path(arguments[0]).read_text(encoding="utf-8"))
    SNAPSHOT.write_text(render(project(catalogue), arguments[1]), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
