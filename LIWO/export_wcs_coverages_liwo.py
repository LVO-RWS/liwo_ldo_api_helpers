#!/usr/bin/env python3
"""Exporteer LIWO WCS coverage-ID's.

Gebruik dit script om te zien welke coverage-ID's beschikbaar zijn voor WCS 2.0.1 en 1.0.0.
Resultaat wordt als CSV en JSON opgeslagen.
"""

from __future__ import annotations

import os
from datetime import datetime
from xml.etree import ElementTree as ET

import requests

from _liwo_common import (
    get_base,
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
MAX_CONSOLE_ROWS = 30
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"


def fetch_ids(base: str, version: str, timeout: int) -> list[str]:
    """Fetch ids.

    Parameters
    ----------
    base : str
        Base URL for the request.
    version : str
        Dataset version to download.
    timeout : int
        Timeout in seconds.

    Returns
    -------
    list[str]
        Collected items.
    """
    response = requests.get(
        f"{base}/wcs",
        params={"service": "WCS", "request": "GetCapabilities", "version": version},
        timeout=timeout,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)

    if version == "2.0.1":
        ns = {"wcs": "http://www.opengis.net/wcs/2.0"}
        return sorted(
            {
                (el.text or "").strip()
                for el in root.findall(".//wcs:CoverageSummary/wcs:CoverageId", ns)
                if (el.text or "").strip()
            }
        )

    ns = {"wcs": "http://www.opengis.net/wcs"}
    return sorted(
        {
            (el.text or "").strip()
            for el in root.findall(".//wcs:CoverageOfferingBrief/wcs:name", ns)
            if (el.text or "").strip()
        }
    )


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()

    versions = ["2.0.1"] if SMOKE_MODE else ["2.0.1", "1.0.0"]
    ids_by_version = {version: fetch_ids(BASE_URL, version, TIMEOUT_SEC) for version in versions}
    ids_201 = ids_by_version.get("2.0.1", [])
    ids_100 = ids_by_version.get("1.0.0", [])

    rows = (
        [{"version": "2.0.1", "coverage_id": coverage_id} for coverage_id in ids_201]
        + [{"version": "1.0.0", "coverage_id": coverage_id} for coverage_id in ids_100]
    )
    csv_path = output_file("liwo_wcs_coverages.csv")
    json_path = output_file("liwo_wcs_coverages.json")

    write_csv(csv_path, rows, ["version", "coverage_id"])
    write_json(
        json_path,
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "v2_0_1_count": len(ids_201),
            "v1_0_0_count": len(ids_100),
            "v2_0_1": ids_201,
            "v1_0_0": ids_100,
        },
    )

    print("WCS coverages (voorbeeld):")
    print_table(rows, [("version", "version", 8), ("coverage_id", "coverage_id", 70)], MAX_CONSOLE_ROWS)
    print("")
    print_json_block(
        "WCS-coverages samenvatting:",
        {
            "smoke_mode": SMOKE_MODE,
            "v2_0_1_count": len(ids_201),
            "v1_0_0_count": len(ids_100),
        },
    )
    print(f"Wrote: {csv_path}")
    print(f"Wrote: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
