#!/usr/bin/env python3
"""Download GeoTIFFs voor de eerder gevonden LDO crossborder scenario's."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

LDO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "LDO")
sys.path.insert(0, str(LDO_ROOT))

from _ldo_common import print_json_block
from _ldo_crossborder_common import (
    crossborder_run_dir,
    download_file,
    latest_crossborder_file,
)

# Instellingen
SCRIPT_STEM = Path(__file__).stem
INPUT_CSV = latest_crossborder_file(
    "02_export_scenarios_grensoverschrijdend_ldo",
    "scenarios_cross_border_and_de_only.csv",
)
OVERSCHRIJF_BESTAANDE_BESTANDEN = False
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    output_dir = crossborder_run_dir(SCRIPT_STEM) / "tifs"
    if not INPUT_CSV.exists():
        if SMOKE_MODE:
            print_json_block(
                "Crossborder TIFF download samenvatting:",
                {
                    "smoke_mode": True,
                    "rows_selected": 0,
                    "downloaded": 0,
                    "skipped_existing": 0,
                    "failed": 0,
                    "input_csv": str(INPUT_CSV),
                    "output_dir": str(output_dir),
                },
            )
            return 0
        raise SystemExit(f"Input CSV ontbreekt: {INPUT_CSV}")

    dataframe = pd.read_csv(INPUT_CSV)

    if SMOKE_MODE:
        print_json_block(
            "Crossborder TIFF download samenvatting:",
            {
                "smoke_mode": True,
                "rows_selected": len(dataframe),
                "downloaded": 0,
                "skipped_existing": 0,
                "failed": 0,
                "input_csv": str(INPUT_CSV),
                "output_dir": str(output_dir),
            },
        )
        return 0

    downloaded = 0
    skipped = 0
    failed = 0

    for _, row in dataframe.iterrows():
        tif_url = str(row.get("tif_url", "")).strip()
        tif_name = str(row.get("tif_name", "")).strip()
        scenario_id = int(row["scenario_id"])
        if not tif_url or not tif_name:
            failed += 1
            continue

        destination = output_dir / f"{scenario_id}_{Path(tif_name).name}"
        if destination.exists() and not OVERSCHRIJF_BESTAANDE_BESTANDEN:
            skipped += 1
            continue

        try:
            download_file(tif_url, destination)
            downloaded += 1
        except Exception as exc:
            failed += 1
            print(f"Download mislukt voor scenario {scenario_id}: {exc}")

    print_json_block(
        "Crossborder TIFF download samenvatting:",
        {
            "rows_selected": len(dataframe),
            "downloaded": downloaded,
            "skipped_existing": skipped,
            "failed": failed,
            "input_csv": str(INPUT_CSV),
            "output_dir": str(output_dir),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
