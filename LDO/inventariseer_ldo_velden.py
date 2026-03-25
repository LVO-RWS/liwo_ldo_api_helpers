#!/usr/bin/env python3
"""Laat van één LDO-scenario alle beschikbare veldpaden zien.

Gebruik dit script als je snel wilt zien welke velden er zijn in:
- het scenario-object zelf
- de scenario-meta
- files, rasters en breaches
- external-processings en hun meta_data

De output komt:
- als boomstructuur in de console
- als boomstructuur en als simpele tekstlijst in `output/ldo/...`
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from _ldo_common import (
    api_url,
    get_base,
    get_token,
    load_env_fallback,
    make_session,
    output_file,
    print_json_block,
)

# Instellingen
BASE_URL = get_base()
SCENARIO_ID = 20022
EXTERNAL_LIMIT = 200
EXTERNAL_OFFSET = 0


def value_type(value: Any) -> str:
    """Return a compact type label for a value.

    Parameters
    ----------
    value : Any
        Value to inspect or format.

    Returns
    -------
    str
        Text result.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__


def collect_field_paths(
    value: Any,
    path: str,
    field_types: dict[str, set[str]],
) -> None:
    """Collect field paths and observed value types.

    Parameters
    ----------
    value : Any
        Value to inspect or format.
    path : str
        Target path for this operation.
    field_types : dict[str, set[str]]
        Observed value types per field.
    """
    field_types[path].add(value_type(value))

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            collect_field_paths(child, child_path, field_types)
        return

    if isinstance(value, list):
        item_path = f"{path}[]"
        for item in value:
            collect_field_paths(item, item_path, field_types)


def split_field_path(field_path: str) -> list[str]:
    """Split a field path into tree tokens.

    Parameters
    ----------
    field_path : str
        Flattened field path such as `scenario.meta.key` or `files[]`.

    Returns
    -------
    list[str]
        Ordered tree tokens for the path.
    """
    tokens: list[str] = []
    for part in field_path.split("."):
        if not part:
            continue
        head = part
        while head.endswith("[]") and head != "[]":
            base = head[:-2]
            if base:
                tokens.append(base)
            tokens.append("[]")
            head = ""
        if head:
            tokens.append(head)
    return tokens


def build_field_tree(field_types: dict[str, set[str]]) -> dict[str, dict[str, Any]]:
    """Build a nested tree from flat field paths.

    Parameters
    ----------
    field_types : dict[str, set[str]]
        Observed value types keyed by flat field path.

    Returns
    -------
    dict[str, dict[str, Any]]
        Nested tree structure for rendering.
    """
    tree: dict[str, dict[str, Any]] = {}
    for field_path, types in field_types.items():
        node_map = tree
        for token in split_field_path(field_path):
            node = node_map.setdefault(token, {"types": set(), "children": {}})
            node["types"].update(types)
            node_map = node["children"]
    return tree


def render_tree_lines(tree: dict[str, dict[str, Any]]) -> list[str]:
    """Render a nested field tree as ASCII lines.

    Parameters
    ----------
    tree : dict[str, dict[str, Any]]
        Nested tree structure built from field paths.

    Returns
    -------
    list[str]
        Rendered tree lines.
    """
    lines: list[str] = []

    def node_label(name: str, types: set[str]) -> str:
        """Build the display label for one tree node."""
        type_text = ", ".join(sorted(types)) if types else "<unknown>"
        return f"{name} ({type_text})"

    def render_children(
        children: dict[str, dict[str, Any]],
        prefix: str,
    ) -> None:
        """Render child nodes recursively."""
        items = list(children.items())
        for index, (name, node) in enumerate(items):
            is_last = index == len(items) - 1
            connector = "\\-- " if is_last else "|-- "
            lines.append(f"{prefix}{connector}{node_label(name, node['types'])}")
            child_prefix = prefix + ("    " if is_last else "|   ")
            render_children(node["children"], child_prefix)

    root_items = list(tree.items())
    for index, (name, node) in enumerate(root_items):
        lines.append(node_label(name, node["types"]))
        if node["children"]:
            render_children(node["children"], "")
        if index != len(root_items) - 1:
            lines.append("")

    return lines


def write_text_list(path: Path, lines: list[str]) -> None:
    """Write plain text lines to disk.

    Parameters
    ----------
    path : Path
        Target path for this operation.
    lines : list[str]
        Text lines to write to the output file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()

    token = get_token(required=True)
    session = make_session(token)

    scenario_response = session.get(
        api_url(BASE_URL, f"scenarios/{SCENARIO_ID}"),
        timeout=60,
    )
    scenario_response.raise_for_status()
    scenario_payload = scenario_response.json()

    external_response = session.get(
        api_url(BASE_URL, f"scenarios/{SCENARIO_ID}/external-processings"),
        params={"limit": EXTERNAL_LIMIT, "offset": EXTERNAL_OFFSET},
        timeout=60,
    )
    external_response.raise_for_status()
    external_payload = external_response.json()
    external_items = []
    if isinstance(external_payload, dict) and isinstance(external_payload.get("items"), list):
        external_items = external_payload["items"]

    field_types: dict[str, set[str]] = defaultdict(set)
    collect_field_paths(scenario_payload, "scenario", field_types)
    collect_field_paths(external_items, "external_processings", field_types)

    flat_lines = [
        f"{field_path} | {', '.join(sorted(types))}"
        for field_path, types in field_types.items()
    ]
    tree_lines = render_tree_lines(build_field_tree(field_types))

    flat_output_path = output_file(f"scenario_{SCENARIO_ID}_velden.txt")
    tree_output_path = output_file(f"scenario_{SCENARIO_ID}_velden_tree.txt")
    write_text_list(flat_output_path, flat_lines)
    write_text_list(tree_output_path, tree_lines)

    print_json_block(
        "LDO-velden samenvatting:",
        {
            "scenario_id": SCENARIO_ID,
            "aantal_veldpaden": len(flat_lines),
            "tree_bestand": str(tree_output_path),
            "plat_bestand": str(flat_output_path),
        },
    )
    print("")
    print("Boomstructuur van gevonden velden:")
    for line in tree_lines:
        print(line)
    print("")
    print(f"Wrote: {tree_output_path}")
    print(f"Wrote: {flat_output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
