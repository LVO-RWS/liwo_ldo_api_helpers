#!/usr/bin/env python3
"""Download één LIWO WCS coverage als GeoTIFF.

Gebruik dit script om een specifieke coverage-ID als rasterbestand op te halen.
Pas bovenin coverage-ID, WCS-versie en bestandsnaam aan.
"""

from __future__ import annotations

import os
import requests

from _liwo_common import get_base, load_env_fallback, output_file, print_json_block

# Instellingen
BASE_URL = get_base()
COVERAGE_ID = "LIWO_Regionaal__scenario_10000"
WCS_VERSIE = "2.0.1"  # "2.0.1" of "1.0.0"
UITVOER_BESTANDSNAAM = "coverage.tif"
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()
    out_path = output_file(UITVOER_BESTANDSNAAM)

    endpoint = f"{BASE_URL}/wcs"
    if WCS_VERSIE == "2.0.1":
        params = {
            "service": "WCS",
            "request": "GetCoverage",
            "version": "2.0.1",
            "coverageId": COVERAGE_ID,
            "format": "image/geotiff",
            "outputCRS": "EPSG:28992",
        }
    else:
        params = {
            "service": "WCS",
            "request": "GetCoverage",
            "version": "1.0.0",
            "coverage": COVERAGE_ID,
            "format": "GeoTIFF",
        }

    if SMOKE_MODE:
        print_json_block(
            "WCS-download samenvatting:",
            {
                "coverage_id": COVERAGE_ID,
                "wcs_version": WCS_VERSIE,
                "smoke_mode": True,
                "download_skipped": True,
                "output_path": str(out_path),
            },
        )
        return 0

    response = requests.get(endpoint, params=params, timeout=180, stream=True)
    response.raise_for_status()

    with out_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    print_json_block(
        "WCS-download samenvatting:",
        {
            "coverage_id": COVERAGE_ID,
            "wcs_version": WCS_VERSIE,
            "size_bytes": out_path.stat().st_size if out_path.exists() else 0,
        },
    )
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
