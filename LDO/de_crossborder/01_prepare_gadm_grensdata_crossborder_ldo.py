#!/usr/bin/env python3
"""Download GADM grensdata voor de LDO NL-DE crossborder workflow."""

from __future__ import annotations

import os
import sys
from pathlib import Path

LDO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "LDO")
sys.path.insert(0, str(LDO_ROOT))

from _ldo_common import print_json_block
from _ldo_crossborder_common import CROSSBORDER_SRC_DIR, download_gadm_shapefile

# Instellingen
GADM_VERSION = "4.1"
DOWNLOAD_OPNIEUW = False
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    outputs: list[dict[str, str]] = []
    for country_code in ("NLD", "DEU"):
        target_dir = CROSSBORDER_SRC_DIR / f"gadm_{country_code}_shp"
        shp_name = f"gadm{GADM_VERSION.replace('.', '')}_{country_code}_0.shp"
        if SMOKE_MODE:
            outputs.append(
                {
                    "country_code": country_code,
                    "status": "available" if target_dir.exists() else "smoke_skip_download",
                    "path": str(target_dir / shp_name),
                }
            )
            continue
        if target_dir.exists() and list(target_dir.glob("*.shp")) and not DOWNLOAD_OPNIEUW:
            outputs.append(
                {
                    "country_code": country_code,
                    "status": "bestaat_al",
                    "path": str(target_dir),
                }
            )
            continue

        download_gadm_shapefile(country_code, target_dir, GADM_VERSION)
        outputs.append(
            {
                "country_code": country_code,
                "status": "gedownload",
                "path": str(target_dir / shp_name),
            }
        )

    print_json_block("GADM download samenvatting:", {"items": outputs})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
