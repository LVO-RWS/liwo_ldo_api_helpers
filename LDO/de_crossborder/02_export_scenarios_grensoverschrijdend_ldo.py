#!/usr/bin/env python3
"""Maak een eenvoudige NL-DE crossborder scenario-export vanuit LDO."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys
from pathlib import Path

import pandas as pd

LDO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "LDO")
sys.path.insert(0, str(LDO_ROOT))

from _ldo_common import print_json_block
from _ldo_crossborder_common import (
    RDNEW,
    classify_scenario_for_de_crossborder,
    crossborder_output_file,
    crossborder_run_dir,
    download_all_scenarios_excel,
    make_ldo_session,
    read_country_layers,
    read_export_metadata,
    unary_union,
)

# Instellingen
SCRIPT_STEM = Path(__file__).stem
DIEPTE_HINT = "Maximale_overstromingsdiepte"
DEELSTAAT_NAAM = "Nordrhein-Westfalen"
MIN_POSITIEVE_DIEPTE = 0.00000001
MIN_POSITIEVE_PIXELS = 50
MAX_SCENARIOS = 0  # 0 = alles
AANTAL_WORKERS = 8
FOUT_HERKANSING_WORKERS = 1
VOORTGANGS_INTERVAL = 100
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    output_dir = crossborder_run_dir(SCRIPT_STEM)
    uitvoer_excel = crossborder_output_file("all_scenarios.xlsx", SCRIPT_STEM)
    uitvoer_metadata_csv = crossborder_output_file("all_scenarios_meta.csv", SCRIPT_STEM)
    uitvoer_crossborder_en_de_only_csv = crossborder_output_file(
        "scenarios_cross_border_and_de_only.csv",
        SCRIPT_STEM,
    )
    uitvoer_crossborder_csv = crossborder_output_file(
        "scenarios_cross_border_only.csv",
        SCRIPT_STEM,
    )
    uitvoer_failed_csv = crossborder_output_file(
        "failed_scenarios.csv",
        SCRIPT_STEM,
    )
    if SMOKE_MODE:
        lege_flags = pd.DataFrame(
            columns=[
                "scenario_id",
                "scenarionaam",
                "naam_doorbraaklocatie",
                "x_rdnew",
                "y_rdnew",
                "category",
                "tif_name",
                "tif_url",
                "de_valid",
                "de_positive",
                "nl_valid",
                "nl_positive",
            ]
        )
        lege_flags.to_csv(
            uitvoer_crossborder_en_de_only_csv,
            index=False,
            encoding="utf-8-sig",
        )
        lege_flags.to_csv(uitvoer_crossborder_csv, index=False, encoding="utf-8-sig")
        pd.DataFrame(
            columns=["scenario_id", "error", "attempts", "retryable", "last_pass"]
        ).to_csv(uitvoer_failed_csv, index=False, encoding="utf-8-sig")
        pd.DataFrame(
            columns=[
                "scenario_id",
                "scenarionaam",
                "projectnaam",
                "eigenaar",
                "naam_buitenwater",
                "naam_doorbraaklocatie",
                "x_rdnew",
                "y_rdnew",
            ]
        ).to_csv(uitvoer_metadata_csv, index=False, encoding="utf-8-sig")
        pd.DataFrame(columns=["scenario_id"]).to_excel(uitvoer_excel, index=False)
        print_json_block(
            "Crossborder samenvatting:",
            {
                "smoke_mode": True,
                "cross_border_and_de_only_rows": 0,
                "de_only_rows": 0,
                "cross_border_rows": 0,
                "output_dir": str(output_dir),
                "excel_output": str(uitvoer_excel),
                "metadata_output": str(uitvoer_metadata_csv),
                "cross_border_and_de_only_output": str(uitvoer_crossborder_en_de_only_csv),
                "cross_border_output": str(uitvoer_crossborder_csv),
                "failed_output": str(uitvoer_failed_csv),
            },
        )
        return 0

    base_url, session = make_ldo_session()
    token = session.headers.get("authorization", "").replace("Bearer ", "", 1).strip()
    if not token:
        raise SystemExit("Geen LDO token gevonden in de sessieheaders.")

    print("Stap 1/4: download Excel export...")
    download_all_scenarios_excel(session, base_url, uitvoer_excel)

    print("Stap 2/4: maak compacte metadata CSV...")
    metadata = read_export_metadata(uitvoer_excel)
    metadata.to_csv(uitvoer_metadata_csv, index=False, encoding="utf-8-sig")

    print("Stap 3/4: laad NL en NRW grenzen...")
    gdf_nl, gdf_de = read_country_layers()
    gdf_de = gdf_de[gdf_de["NAME_1"] == DEELSTAAT_NAAM].copy()
    if gdf_de.empty:
        raise SystemExit(f"Deelstaat niet gevonden in shapefile: {DEELSTAAT_NAAM}")

    nl_geom = unary_union(gdf_nl.geometry.values)
    de_geom = unary_union(gdf_de.geometry.values)

    print("Stap 4/4: scan scenario's op positieve dieptepixels in DE en daarna NL voor DE-hits...")
    scenario_ids = metadata["scenario_id"].astype(int).tolist()
    if MAX_SCENARIOS > 0:
        scenario_ids = scenario_ids[:MAX_SCENARIOS]

    rows_by_scenario: dict[int, dict[str, object]] = {}
    missing_tif = 0
    outside_de_bounds = 0
    no_positive_de = 0
    de_only_count = 0
    cross_border_count = 0
    max_workers = max(1, min(AANTAL_WORKERS, len(scenario_ids) or 1))

    def handle_non_error_result(result: dict[str, object]) -> None:
        """Update counters and collected rows for one final classification result."""
        nonlocal missing_tif, outside_de_bounds, no_positive_de, de_only_count, cross_border_count

        status = str(result.get("status", ""))
        if status == "missing_tif":
            missing_tif += 1
            return
        if status == "outside_de_bounds":
            outside_de_bounds += 1
            return
        if status == "no_positive_de":
            no_positive_de += 1
            return
        if status not in {"de_only", "cross_border"}:
            return

        row = result.get("row", {})
        if not isinstance(row, dict):
            return
        scenario_id = int(row.get("scenario_id", result.get("scenario_id", 0)) or 0)
        if status == "de_only":
            de_only_count += 1
        else:
            cross_border_count += 1
        rows_by_scenario[scenario_id] = dict(row)

    def run_scan_pass(
        ids_for_pass: list[int],
        worker_count: int,
        pass_name: str,
        progress_interval: int,
    ) -> list[dict[str, object]]:
        """Run one scan pass and return the scenarios that still ended in error."""
        if not ids_for_pass:
            return []

        failed_results: list[dict[str, object]] = []
        completed = 0
        effective_workers = max(1, min(worker_count, len(ids_for_pass) or 1))
        progress_prefix = "Bezig" if pass_name == "eerste_scan" else "Herkansing"

        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            futures = {
                executor.submit(
                    classify_scenario_for_de_crossborder,
                    base_url=base_url,
                    token=token,
                    scenario_id=scenario_id,
                    de_geom=de_geom,
                    nl_geom=nl_geom,
                    geom_crs=RDNEW,
                    depth_hint=DIEPTE_HINT,
                    min_positive_depth=MIN_POSITIEVE_DIEPTE,
                    min_positive_pixels=MIN_POSITIEVE_PIXELS,
                ): scenario_id
                for scenario_id in ids_for_pass
            }
            for future in as_completed(futures):
                scenario_id = futures[future]
                completed += 1
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "scenario_id": scenario_id,
                        "status": "error",
                        "error": str(exc),
                        "attempts": 0,
                        "retryable": False,
                    }

                status = str(result.get("status", "")) if isinstance(result, dict) else "error"
                if status == "error":
                    error_text = (
                        str(result.get("error", "")).strip()
                        if isinstance(result, dict)
                        else ""
                    ) or "Onbekende fout"
                    failed_results.append(
                        {
                            "scenario_id": scenario_id,
                            "error": error_text,
                            "attempts": int(result.get("attempts", 0) or 0),
                            "retryable": bool(result.get("retryable", False)),
                            "last_pass": pass_name,
                        }
                    )
                    if len(failed_results) <= 10:
                        print(f"{progress_prefix} scenario {scenario_id} faalde: {error_text}")
                else:
                    handle_non_error_result(result)

                if completed % progress_interval == 0 or completed == len(ids_for_pass):
                    print(
                        f"{progress_prefix}: {completed}/{len(ids_for_pass)} | "
                        f"CROSS_BORDER={cross_border_count} | DE_ONLY={de_only_count}"
                    )

        return failed_results

    first_pass_failures = run_scan_pass(
        scenario_ids,
        max_workers,
        "eerste_scan",
        VOORTGANGS_INTERVAL,
    )

    final_failures = first_pass_failures
    if first_pass_failures:
        retry_ids = [int(item["scenario_id"]) for item in first_pass_failures]
        print(
            f"Herkansing: probeer {len(retry_ids)} tijdelijk mislukte scenario's opnieuw "
            f"met {FOUT_HERKANSING_WORKERS} worker(s)..."
        )
        final_failures = run_scan_pass(
            retry_ids,
            FOUT_HERKANSING_WORKERS,
            "herkansing",
            max(1, min(25, len(retry_ids))),
        )

    failed_df = pd.DataFrame(
        final_failures,
        columns=["scenario_id", "error", "attempts", "retryable", "last_pass"],
    ).sort_values("scenario_id").reset_index(drop=True)
    failed_df.to_csv(uitvoer_failed_csv, index=False, encoding="utf-8-sig")

    result_df = pd.DataFrame(
        list(rows_by_scenario.values()),
        columns=[
            "scenario_id",
            "category",
            "tif_name",
            "tif_url",
            "de_valid",
            "de_positive",
            "nl_valid",
            "nl_positive",
        ],
    ).sort_values("scenario_id").reset_index(drop=True)
    if result_df.empty:
        crossborder_en_de_only = metadata.merge(result_df, on="scenario_id", how="inner")
        crossborder_only = crossborder_en_de_only.head(0).copy()
    else:
        crossborder_en_de_only = metadata.merge(result_df, on="scenario_id", how="inner")
        crossborder_en_de_only = crossborder_en_de_only.sort_values("scenario_id").reset_index(drop=True)
        crossborder_only = crossborder_en_de_only[
            crossborder_en_de_only["category"] == "CROSS_BORDER"
        ].copy()

    crossborder_en_de_only.to_csv(
        uitvoer_crossborder_en_de_only_csv,
        index=False,
        encoding="utf-8-sig",
    )
    crossborder_only.to_csv(uitvoer_crossborder_csv, index=False, encoding="utf-8-sig")

    counts = {"CROSS_BORDER": cross_border_count, "DE_ONLY": de_only_count}
    retry_candidates = len(first_pass_failures)
    resolved_after_retry = retry_candidates - len(final_failures)
    print_json_block(
        "Crossborder samenvatting:",
        {
            "scenarios_scanned": len(scenario_ids),
            "scan_workers": max_workers,
            "retry_candidates": retry_candidates,
            "retry_resolved": resolved_after_retry,
            "retry_workers": FOUT_HERKANSING_WORKERS,
            "missing_depth_tif": missing_tif,
            "outside_de_bounds": outside_de_bounds,
            "no_positive_depth_in_de": no_positive_de,
            "errors_after_retry": len(final_failures),
            "cross_border_and_de_only_rows": len(crossborder_en_de_only),
            "de_only_rows": de_only_count,
            "cross_border_rows": len(crossborder_only),
            "category_counts": counts,
            "output_dir": str(output_dir),
            "excel_output": str(uitvoer_excel),
            "metadata_output": str(uitvoer_metadata_csv),
            "cross_border_and_de_only_output": str(uitvoer_crossborder_en_de_only_csv),
            "cross_border_output": str(uitvoer_crossborder_csv),
            "failed_output": str(uitvoer_failed_csv),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
