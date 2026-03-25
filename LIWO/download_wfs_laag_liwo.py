#!/usr/bin/env python3
"""Download één LIWO WFS-laag naar GeoPackage.

Gebruik dit script voor een snelle download van een vectorlaag uit LIWO.
Pas alleen workspace, laagnaam en bestandsnaam bovenin aan.
"""

from __future__ import annotations

import os
from urllib.parse import quote_plus

from _liwo_common import get_base, load_env_fallback, output_file, print_json_block

# Instellingen
BASE_URL = get_base()
WORKSPACE = "LIWO_Basis"
LAAGNAAM = "LIWO_Basis:overstromingskansen_actueel_2019_faalkans_primair"
BESTANDSNAAM = "wfs_layer.gpkg"
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()
    out_path = output_file(BESTANDSNAAM)
    wfs_url = f"{BASE_URL}/{WORKSPACE}/wfs"
    url = (
        f"{wfs_url}?service=WFS&version=2.0.0&request=GetFeature"
        f"&typename={quote_plus(LAAGNAAM)}&outputFormat=application/json"
    )
    if SMOKE_MODE:
        print_json_block(
            "WFS-download samenvatting:",
            {
                "workspace": WORKSPACE,
                "layer_name": LAAGNAAM,
                "smoke_mode": True,
                "download_skipped": True,
                "request_url": url,
                "output_path": str(out_path),
            },
        )
        return 0

    try:
        import geopandas as gpd
    except Exception as exc:
        raise SystemExit(
            "This script requires geopandas. Install dependencies from environment.yml first."
        ) from exc

    gdf = gpd.read_file(url)
    gdf.to_file(out_path, driver="GPKG")

    print_json_block(
        "WFS-download samenvatting:",
        {
            "workspace": WORKSPACE,
            "layer_name": LAAGNAAM,
            "rows": len(gdf),
            "crs": str(gdf.crs),
            "columns": [str(c) for c in list(gdf.columns)[:15]],
        },
    )
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
