#!/usr/bin/env python3
"""Exporteer LIWO scenario-ID's per workspace vanuit WMS-lagen.

Gebruik dit script om een complete lijst van `scenario_*` lagen op te bouwen.
De gecombineerde lijst is handig als input voor koppeling met LDO.
"""

from __future__ import annotations

import re

from _liwo_common import (
    get_base,
    get_xml,
    load_env_fallback,
    output_file,
    print_json_block,
    print_table,
    write_csv,
)


DEFAULT_WORKSPACES = ["LIWO_Primair", "LIWO_Regionaal", "LIWO_RegionaalSysteem"]
BASE_URL = get_base()
TIMEOUT_SEC = 30
WORKSPACES = DEFAULT_WORKSPACES
MAX_CONSOLE_ROWS = 25


def parse_layers_from_global_caps(base: str, timeout: int) -> list[str]:
    """Parse layers from global caps.

    Parameters
    ----------
    base : str
        Base URL for the request.
    timeout : int
        Timeout in seconds.

    Returns
    -------
    list[str]
        Collected items.
    """
    root = get_xml(
        f"{base}/wms",
        {"service": "WMS", "request": "GetCapabilities", "version": "1.3.0"},
        timeout=timeout,
    )
    ns = {"wms": "http://www.opengis.net/wms"}
    names = []
    for element in root.findall(".//wms:Layer/wms:Name", ns):
        text = (element.text or "").strip()
        if text:
            names.append(text)
    return names


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()

    layer_names = parse_layers_from_global_caps(BASE_URL, TIMEOUT_SEC)
    by_workspace: dict[str, list[dict[str, str]]] = {ws: [] for ws in WORKSPACES}

    for name in layer_names:
        if ":" not in name:
            continue
        workspace, layer = name.split(":", 1)
        if workspace not in by_workspace:
            continue
        match = re.fullmatch(r"scenario_(\d+)", layer)
        if not match:
            continue
        by_workspace[workspace].append(
            {
                "workspace": workspace,
                "scenario_id": match.group(1),
                "layer_name": name,
            }
        )

    combined: list[dict[str, str]] = []
    for workspace in WORKSPACES:
        rows = sorted(by_workspace[workspace], key=lambda r: int(r["scenario_id"]))
        combined.extend(rows)
        ws_path = output_file(f"{workspace}_scenario_ids.csv")
        write_csv(ws_path, rows, ["workspace", "scenario_id", "layer_name"])
        print(f"{workspace}: {len(rows)} scenario layers -> {ws_path}")

    combined_path = output_file("liwo_scenario_ids_all.csv")
    write_csv(
        combined_path,
        sorted(combined, key=lambda r: (r["workspace"], int(r["scenario_id"]))),
        ["workspace", "scenario_id", "layer_name"],
    )
    combined_sorted = sorted(combined, key=lambda r: (r["workspace"], int(r["scenario_id"])))
    print("")
    print("Voorbeeld scenario IDs:")
    print_table(
        combined_sorted,
        [
            ("workspace", "workspace", 24),
            ("scenario_id", "scenario_id", 12),
            ("layer_name", "layer_name", 40),
        ],
        MAX_CONSOLE_ROWS,
    )
    print("")
    print_json_block(
        "Scenario-ID samenvatting:",
        {
            "total_rows": len(combined_sorted),
            "workspaces": {ws: len(by_workspace[ws]) for ws in WORKSPACES},
        },
    )
    print(f"Combined rows: {len(combined)} -> {combined_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
