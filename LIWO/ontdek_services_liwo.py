#!/usr/bin/env python3
"""Ontdek LIWO workspaces en service-overzicht.

Gebruik dit script om snel te zien welke workspaces beschikbaar zijn.
Optioneel kun je ook aantallen WMS/WFS-lagen laten meetellen.
"""

from __future__ import annotations

from datetime import datetime

from _liwo_common import (
    get_base,
    get_xml,
    local_name,
    load_env_fallback,
    output_file,
    print_json_block,
    print_table,
    write_csv,
    write_json,
)

# Instellingen
BASE_URL = get_base()
TIMEOUT_SEC = 30
TEL_WMS_LAGEN = False
TEL_OOK_WFS_LAGEN = False
MAX_CONSOLE_ROWS = 30


def discover_workspaces(base: str, timeout: int) -> list[str]:
    """Discover workspaces.

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
    found: set[str] = set()
    for element in root.iter():
        if local_name(element.tag) != "Name":
            continue
        text = (element.text or "").strip()
        if ":" not in text:
            continue
        workspace = text.split(":", 1)[0].strip()
        if workspace:
            found.add(workspace)
    return sorted(found)


def count_layers(base: str, workspace: str, service: str, timeout: int) -> int:
    """Count layers.

    Parameters
    ----------
    base : str
        Base URL for the request.
    workspace : str
        Workspace name to inspect.
    service : str
        Service record or service name to inspect.
    timeout : int
        Timeout in seconds.

    Returns
    -------
    int
        Integer result.
    """
    version = "1.3.0" if service == "WMS" else "2.0.0"
    endpoint = f"{base}/{workspace}/{service.lower()}"
    root = get_xml(
        endpoint,
        {"service": service, "request": "GetCapabilities", "version": version},
        timeout=timeout,
    )
    names: set[str] = set()
    for element in root.iter():
        if local_name(element.tag) != "Name":
            continue
        text = (element.text or "").strip()
        if text:
            names.add(text)
    return len(names)


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()

    workspaces = discover_workspaces(BASE_URL, TIMEOUT_SEC)
    rows: list[dict[str, str]] = []
    for workspace in workspaces:
        if TEL_WMS_LAGEN:
            try:
                wms_count = count_layers(BASE_URL, workspace, "WMS", TIMEOUT_SEC)
            except Exception:
                wms_count = -1
        else:
            wms_count = -1
        if TEL_WMS_LAGEN and TEL_OOK_WFS_LAGEN:
            try:
                wfs_count = count_layers(BASE_URL, workspace, "WFS", TIMEOUT_SEC)
            except Exception:
                wfs_count = -1
        else:
            wfs_count = -1
        rows.append(
            {
                "workspace": workspace,
                "wms_layer_count": str(wms_count),
                "wfs_layer_count": str(wfs_count),
            }
        )

    csv_path = output_file("liwo_workspaces_service_counts.csv")
    json_path = output_file("liwo_workspaces_service_counts.json")

    write_csv(csv_path, rows, ["workspace", "wms_layer_count", "wfs_layer_count"])
    write_json(
        json_path,
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "workspace_count": len(rows),
            "items": rows,
        },
    )

    print("LIWO workspaces:")
    print_table(
        rows,
        [
            ("workspace", "workspace", 24),
            ("wms_layer_count", "wms_count", 10),
            ("wfs_layer_count", "wfs_count", 10),
        ],
        MAX_CONSOLE_ROWS,
    )
    print("")
    print_json_block(
        "Discovery-samenvatting:",
        {
            "workspace_count": len(rows),
            "wms_count_enabled": TEL_WMS_LAGEN,
            "wfs_count_enabled": TEL_WMS_LAGEN and TEL_OOK_WFS_LAGEN,
        },
    )
    print(f"Wrote: {csv_path}")
    print(f"Wrote: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
