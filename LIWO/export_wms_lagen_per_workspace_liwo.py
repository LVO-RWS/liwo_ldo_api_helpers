#!/usr/bin/env python3
"""Exporteer alle WMS-lagen van één LIWO-workspace.

Gebruik dit script als je de volledige lagenlijst van een workspace nodig hebt.
Pas bovenin alleen de workspace-naam aan.
"""

from __future__ import annotations

from _liwo_common import (
    get_base,
    get_xml,
    load_env_fallback,
    output_file,
    print_json_block,
    print_table,
    write_csv,
)

# Instellingen
BASE_URL = get_base()
WORKSPACE = "LIWO_Primair"
TIMEOUT_SEC = 30
MAX_CONSOLE_ROWS = 30


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()

    root = get_xml(
        f"{BASE_URL}/{WORKSPACE}/wms",
        {"service": "WMS", "request": "GetCapabilities", "version": "1.3.0"},
        timeout=TIMEOUT_SEC,
    )
    ns = {"wms": "http://www.opengis.net/wms"}
    names = sorted(
        {
            (element.text or "").strip()
            for element in root.findall(".//wms:Layer/wms:Name", ns)
            if (element.text or "").strip()
        }
    )
    rows = [{"workspace": WORKSPACE, "layer_name": name} for name in names]

    out_path = output_file(f"{WORKSPACE}_wms_layers.csv")
    write_csv(out_path, rows, ["workspace", "layer_name"])

    print("WMS lagen:")
    print_table(rows, [("workspace", "workspace", 24), ("layer_name", "layer_name", 65)], MAX_CONSOLE_ROWS)
    print("")
    print_json_block(
        "WMS-lagen samenvatting:",
        {"workspace": WORKSPACE, "layer_count": len(rows)},
    )
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
