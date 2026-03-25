#!/usr/bin/env python3
"""Maak een eenvoudige kaart van CROSS_BORDER + DE_ONLY LDO scenario's rond NRW."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

LDO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "LDO")
sys.path.insert(0, str(LDO_ROOT))

from _ldo_common import print_json_block
from _ldo_crossborder_common import (
    crossborder_output_file,
    crossborder_run_dir,
    latest_crossborder_file,
)

# Instellingen
SCRIPT_STEM = Path(__file__).stem
INPUT_CSV = latest_crossborder_file(
    "02_export_scenarios_grensoverschrijdend_ldo",
    "scenarios_cross_border_and_de_only.csv",
)
X_COLUMN = "x_rdnew"
Y_COLUMN = "y_rdnew"
GROUP_COLUMN = "naam_doorbraaklocatie"
NAAM_COLUMN = "scenarionaam"
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    output_dir = crossborder_run_dir(SCRIPT_STEM)
    output_html = crossborder_output_file(
        "scenarios_cross_border_and_de_only_map.html",
        SCRIPT_STEM,
    )
    output_counts_csv = crossborder_output_file(
        "cross_border_and_de_only_doorbraaklocatie_counts.csv",
        SCRIPT_STEM,
    )

    if SMOKE_MODE:
        if not INPUT_CSV.exists():
            print_json_block(
                "Crossborder kaart samenvatting:",
                {
                    "smoke_mode": True,
                    "rows_mapped": 0,
                    "input_csv": str(INPUT_CSV),
                    "output_dir": str(output_dir),
                    "map_output": str(output_html),
                    "counts_output": str(output_counts_csv),
                },
            )
            return 0
        dataframe = pd.read_csv(INPUT_CSV)
        print_json_block(
            "Crossborder kaart samenvatting:",
            {
                "smoke_mode": True,
                "rows_mapped": len(dataframe),
                "input_csv": str(INPUT_CSV),
                "output_dir": str(output_dir),
                "map_output": str(output_html),
                "counts_output": str(output_counts_csv),
            },
        )
        return 0

    try:
        import folium
        from folium.plugins import MarkerCluster
        from pyproj import Transformer
    except Exception as exc:
        raise SystemExit(
            "Dit script heeft folium en pyproj nodig. Installeer eerst environment.yml."
        ) from exc

    if not INPUT_CSV.exists():
        raise SystemExit(f"Input CSV ontbreekt: {INPUT_CSV}")

    dataframe = pd.read_csv(INPUT_CSV)
    if "category" in dataframe.columns:
        dataframe = dataframe[dataframe["category"].isin(["CROSS_BORDER", "DE_ONLY"])].copy()
    dataframe[X_COLUMN] = pd.to_numeric(dataframe[X_COLUMN], errors="coerce")
    dataframe[Y_COLUMN] = pd.to_numeric(dataframe[Y_COLUMN], errors="coerce")
    dataframe = dataframe.dropna(subset=[X_COLUMN, Y_COLUMN]).copy()
    if dataframe.empty:
        raise SystemExit(
            "Geen CROSS_BORDER + DE_ONLY scenario's met geldige RDNew coördinaten gevonden."
        )

    transformer = Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)
    lons, lats = transformer.transform(
        dataframe[X_COLUMN].tolist(),
        dataframe[Y_COLUMN].tolist(),
    )
    dataframe["lon"] = lons
    dataframe["lat"] = lats

    center_lat = float(dataframe["lat"].mean())
    center_lon = float(dataframe["lon"].mean())
    category_colors = {
        "CROSS_BORDER": "red",
        "DE_ONLY": "blue",
        "NL_ONLY": "green",
    }

    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=8, tiles="OpenStreetMap")
    clusters = MarkerCluster(name="Scenario's").add_to(fmap)
    for _, row in dataframe.iterrows():
        category = str(row.get("category", "")).strip()
        color = category_colors.get(category, "gray")
        popup = (
            f"scenario_id: {row.get('scenario_id', '')}<br>"
            f"category: {category}<br>"
            f"scenarionaam: {row.get(NAAM_COLUMN, '')}<br>"
            f"doorbraaklocatie: {row.get(GROUP_COLUMN, '')}"
        )
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            popup=popup,
        ).add_to(clusters)

    if GROUP_COLUMN in dataframe.columns:
        counts = (
            dataframe.groupby(GROUP_COLUMN, dropna=False)
            .size()
            .reset_index(name="scenario_count")
            .sort_values("scenario_count", ascending=False)
        )
        counts.to_csv(output_counts_csv, index=False, encoding="utf-8-sig")
    else:
        counts = pd.DataFrame(columns=[GROUP_COLUMN, "scenario_count"])

    output_dir.mkdir(parents=True, exist_ok=True)
    fmap.save(output_html)

    print_json_block(
        "Crossborder kaart samenvatting:",
        {
            "rows_mapped": len(dataframe),
            "input_csv": str(INPUT_CSV),
            "output_dir": str(output_dir),
            "map_output": str(output_html),
            "counts_output": str(output_counts_csv),
        },
    )
    if not counts.empty:
        print(counts.head(10).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
