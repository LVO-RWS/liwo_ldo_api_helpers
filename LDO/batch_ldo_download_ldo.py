#!/usr/bin/env python3
"""Download meerdere LDO scenario's inclusief files en maak één Excel-overzicht.

Gebruik dit script als je voor een vaste lijst scenario-ID's:
- alle files wilt downloaden
- per scenario een eigen map wilt hebben
- één overzichtelijke Excel wilt met alle relevante scenario-, meta-, file- en external-processing velden

Alle instellingen staan bewust bovenin dit script.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from _ldo_common import (
    api_url,
    get_base,
    get_token,
    load_env_fallback,
    make_session,
    output_run_dir,
    print_json_block,
    print_table,
    write_csv,
    write_excel,
    write_json,
)

# Instellingen
BASE_URL = get_base()
SCENARIO_IDS = [
    20069,
    20070,
]
DOWNLOAD_BESTANDEN = True
REQUEST_TIMEOUT_SEC = 60
DOWNLOAD_TIMEOUT_SEC = 180
STOP_BIJ_EERSTE_FOUT = False
MAX_CONSOLE_ROWS = 50
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"
SMOKE_MAX_SCENARIOS = int(os.getenv("LIWO_LDO_SMOKE_MAX_SCENARIOS", "1"))

# Veldselectie
# - Voor een selectieve export: comment regels uit in de lijst hieronder.
# - Zet `NEEM_ALLE_VELDEN_MEE` op True als je altijd alle mogelijke velden uit de API wilt meenemen, ongeacht wat je hieronder selecteert.
NEEM_ALLE_VELDEN_MEE = True

LDO_VELDEN = [
    # Scenario
    "scenario.id",
    "scenario.tenant",
    "scenario.name",
    "scenario.area_name",
    "scenario.status",
    "scenario.status_detail",
    "scenario.scenario_type",
    "scenario.inundation_source",
    "scenario.meta_version",
    "scenario.excel_import_id",
    "scenario.breach_growth_start",
    "scenario.created_at",
    "scenario.created_by.id",
    "scenario.created_by.name",
    "scenario.updated_at",
    "scenario.updated_by.id",
    "scenario.updated_by.name",
    "scenario.errors",
    "scenario.created_by",
    "scenario.updated_by",
    "scenario.meta",
    "scenario.files",
    "scenario.breaches",
    "scenario.rasters",
    "scenario.json",

    # Metadata
    "meta.scenarionaam",
    "meta.projectnaam",
    "meta.gebiedsnaam",
    "meta.naam buitenwater",
    "meta.naam doorbraaklocatie",
    "meta.x-coordinaten doorbraaklocatie/effectgebied",
    "meta.y-coordinaten doorbraaklocatie/effectgebied",

    # Files
    "files.count",
    "files.names",
    "files.types",
    "files.is_user_input_values",
    "files.created_at_list",
    "files.sizes",
    "files.etags",
    "files.total_size_bytes",
    "files.downloaded_count",
    "files.download_error_count",
    "files.download_errors",
    "files.download_paths",

    # Breaches
    "breaches.count",
    "breaches.lon_list",
    "breaches.lat_list",

    # Rasters
    "rasters.count",
    "rasters.types",
    "rasters.ids",
    "rasters.source_ids",
    "rasters.wms_layers",
    "rasters.names",

    # External processings
    "external.count",
    "external.ids",
    "external.types",
    "external.statuses",
    "external.descriptions",
    "external.created_at_list",
    "external.updated_at_list",
    "external.errors",
    "external.config_json",
    "external.request_error",
    "external.json",

    # External processing meta_data
    "external.meta.Totaalschade",
    "external.meta.Totaal getroffenen",
    "external.meta.Totaal slachtoffers",
]


def cell_text(value: Any) -> str:
    """Return cleaned text for a table cell.

    Parameters
    ----------
    value : Any
        Value to inspect or format.

    Returns
    -------
    str
        Text result.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def join_unique(values) -> str:
    """Join unique values into one text field.

    Parameters
    ----------
    values : Any
        Values to inspect or combine.

    Returns
    -------
    str
        Text result.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = cell_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return " | ".join(ordered)


def resolve_nested_value(data: dict[str, Any], dotted_path: str) -> str:
    """Resolve a nested value from a dotted path.

    Parameters
    ----------
    data : dict[str, Any]
        Input mapping or payload to inspect.
    dotted_path : str
        Dot-separated path to the nested value.

    Returns
    -------
    str
        Text result.
    """
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return ""
        current = current.get(part)
    return cell_text(current)


def selected_prefixed_keys(
    configured_fields: list[str],
    prefix: str,
    found_keys: set[str],
    include_all_found: bool,
) -> list[str]:
    """Return selected keys that match a prefix.

    Parameters
    ----------
    configured_fields : list[str]
        Configured fields to inspect.
    prefix : str
        Field prefix used while flattening.
    found_keys : set[str]
        Keys that were found in the payload.
    include_all_found : bool
        Whether to include every found key instead of the selected subset.

    Returns
    -------
    list[str]
        Collected items.
    """
    selected = [
        field[len(prefix) :]
        for field in configured_fields
        if field.startswith(prefix)
    ]
    if include_all_found:
        for key in sorted(found_keys, key=str.lower):
            if key not in selected:
                selected.append(key)
    return selected


def fetch_scenario(session: requests.Session, base_url: str, scenario_id: int) -> dict[str, Any]:
    """Fetch one scenario payload from the API.

    Parameters
    ----------
    session : requests.Session
        Authenticated requests session.
    base_url : str
        Base URL for the request.
    scenario_id : int
        Scenario identifier.

    Returns
    -------
    dict[str, Any]
        Result dictionary.
    """
    response = session.get(api_url(base_url, f"scenarios/{scenario_id}"), timeout=REQUEST_TIMEOUT_SEC)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Scenario {scenario_id} gaf geen dict terug.")
    return payload


def fetch_external_processings(
    session: requests.Session,
    base_url: str,
    scenario_id: int,
) -> dict[str, Any]:
    """Fetch external processings for one scenario.

    Parameters
    ----------
    session : requests.Session
        Authenticated requests session.
    base_url : str
        Base URL for the request.
    scenario_id : int
        Scenario identifier.

    Returns
    -------
    dict[str, Any]
        Result dictionary.
    """
    response = session.get(
        api_url(base_url, f"scenarios/{scenario_id}/external-processings"),
        params={"limit": 200, "offset": 0},
        timeout=REQUEST_TIMEOUT_SEC,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"External processings voor scenario {scenario_id} gaven geen dict terug.")
    return payload


def download_scenario_file(
    session: requests.Session,
    base_url: str,
    scenario_id: int,
    file_name: str,
    output_path: Path,
) -> int:
    """Download scenario file.

    Parameters
    ----------
    session : requests.Session
        Authenticated requests session.
    base_url : str
        Base URL for the request.
    scenario_id : int
        Scenario identifier.
    file_name : str
        File name to inspect or download.
    output_path : Path
        Output path for the downloaded file.

    Returns
    -------
    int
        Integer result.
    """
    signed_response = session.get(
        api_url(base_url, f"scenarios/{scenario_id}/files/{quote(file_name, safe='')}/download"),
        timeout=REQUEST_TIMEOUT_SEC,
    )
    signed_response.raise_for_status()
    signed_url = signed_response.json().get("url", "")
    if not signed_url:
        raise RuntimeError("Geen signed URL in response.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(signed_url, stream=True, timeout=DOWNLOAD_TIMEOUT_SEC) as response:
        response.raise_for_status()
        with output_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    return output_path.stat().st_size if output_path.exists() else 0


def build_file_rows(
    session: requests.Session,
    base_url: str,
    scenario: dict[str, Any],
    scenario_dir: Path,
    errors: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Build file rows.

    Parameters
    ----------
    session : requests.Session
        Authenticated requests session.
    base_url : str
        Base URL for the request.
    scenario : dict[str, Any]
        Scenario payload to inspect.
    scenario_dir : Path
        Directory for one scenario export.
    errors : list[dict[str, str]]
        Mutable list that collects error messages.

    Returns
    -------
    list[dict[str, str]]
        Collected output rows.
    """
    scenario_id = int(scenario.get("id"))
    scenario_name = str(scenario.get("name", ""))
    files = scenario.get("files", {}) if isinstance(scenario.get("files"), dict) else {}
    rows: list[dict[str, str]] = []

    for file_name in sorted(files.keys()):
        file_info = files.get(file_name, {})
        if not isinstance(file_info, dict):
            file_info = {}
        file_meta = file_info.get("file", {}) if isinstance(file_info.get("file"), dict) else {}

        row = {
            "scenario_id": str(scenario_id),
            "scenario_name": scenario_name,
            "file_name": str(file_name),
            "file_type": str(file_info.get("type", "")),
            "is_user_input": str(file_info.get("is_user_input", "")),
            "file.created_at": str(file_meta.get("created_at", "")),
            "file.size": str(file_meta.get("size", "")),
            "file.etag": str(file_meta.get("etag", "")),
            "download_status": "not_downloaded",
            "download_error": "",
            "download_size_bytes": "",
            "output_path": "",
        }

        if DOWNLOAD_BESTANDEN and not SMOKE_MODE:
            safe_name = Path(str(file_name)).name
            output_path = scenario_dir / safe_name
            try:
                size = download_scenario_file(
                    session=session,
                    base_url=base_url,
                    scenario_id=scenario_id,
                    file_name=str(file_name),
                    output_path=output_path,
                )
                row["download_status"] = "downloaded"
                row["download_size_bytes"] = str(size)
                row["output_path"] = str(output_path)
            except Exception as exc:
                row["download_status"] = "error"
                row["download_error"] = str(exc)
                errors.append(
                    {
                        "scenario_id": str(scenario_id),
                        "stage": "download_file",
                        "item_name": str(file_name),
                        "error": str(exc),
                    }
                )
                if STOP_BIJ_EERSTE_FOUT:
                    raise

        rows.append(row)
    return rows


def build_overview_row(
    scenario: dict[str, Any],
    external_payload: dict[str, Any],
    file_rows: list[dict[str, str]],
    external_request_error: str,
) -> tuple[dict[str, str], set[str], set[str], set[str]]:
    """Build overview row.

    Parameters
    ----------
    scenario : dict[str, Any]
        Scenario payload to inspect.
    external_payload : dict[str, Any]
        External processing payload returned by the API.
    file_rows : list[dict[str, str]]
        Rows that describe scenario files.
    external_request_error : str
        Error from the external-processing request, if any.

    Returns
    -------
    tuple[dict[str, str], set[str], set[str], set[str]]
        Tuple with the requested values.
    """
    row: dict[str, str] = {}

    found_scenario_keys = {str(key) for key in scenario.keys()}
    scenario_fields = selected_prefixed_keys(
        configured_fields=LDO_VELDEN,
        prefix="scenario.",
        found_keys=found_scenario_keys,
        include_all_found=NEEM_ALLE_VELDEN_MEE,
    )
    for path in scenario_fields:
        if path == "json":
            row["scenario.json"] = cell_text(scenario)
        else:
            row[f"scenario.{path}"] = resolve_nested_value(scenario, path)

    meta = scenario.get("meta", {}) if isinstance(scenario.get("meta"), dict) else {}
    found_meta_keys = {str(key) for key in meta.keys()}
    meta_keys = selected_prefixed_keys(
        configured_fields=LDO_VELDEN,
        prefix="meta.",
        found_keys=found_meta_keys,
        include_all_found=NEEM_ALLE_VELDEN_MEE,
    )
    for key in meta_keys:
        row[f"meta.{key}"] = cell_text(meta.get(key, ""))

    scenario_files = scenario.get("files", {}) if isinstance(scenario.get("files"), dict) else {}
    row["files.count"] = str(len(scenario_files))
    row["files.names"] = join_unique(file_row.get("file_name", "") for file_row in file_rows)
    row["files.types"] = join_unique(file_row.get("file_type", "") for file_row in file_rows)
    row["files.is_user_input_values"] = join_unique(file_row.get("is_user_input", "") for file_row in file_rows)
    row["files.created_at_list"] = join_unique(file_row.get("file.created_at", "") for file_row in file_rows)
    row["files.sizes"] = join_unique(file_row.get("file.size", "") for file_row in file_rows)
    row["files.etags"] = join_unique(file_row.get("file.etag", "") for file_row in file_rows)
    row["files.total_size_bytes"] = str(
        sum(int(file_row["file.size"]) for file_row in file_rows if file_row.get("file.size", "").isdigit())
    )
    row["files.downloaded_count"] = str(sum(1 for file_row in file_rows if file_row.get("download_status") == "downloaded"))
    row["files.download_error_count"] = str(sum(1 for file_row in file_rows if file_row.get("download_status") == "error"))
    row["files.download_errors"] = join_unique(file_row.get("download_error", "") for file_row in file_rows)
    row["files.download_paths"] = join_unique(file_row.get("output_path", "") for file_row in file_rows)

    breaches = scenario.get("breaches", []) if isinstance(scenario.get("breaches"), list) else []
    row["breaches.count"] = str(len(breaches))
    row["breaches.lon_list"] = join_unique(
        item.get("lon", "") for item in breaches if isinstance(item, dict)
    )
    row["breaches.lat_list"] = join_unique(
        item.get("lat", "") for item in breaches if isinstance(item, dict)
    )

    rasters = scenario.get("rasters", []) if isinstance(scenario.get("rasters"), list) else []
    row["rasters.count"] = str(len(rasters))
    row["rasters.types"] = join_unique(item.get("type", "") for item in rasters if isinstance(item, dict))
    row["rasters.ids"] = join_unique(item.get("id", "") for item in rasters if isinstance(item, dict))
    row["rasters.source_ids"] = join_unique(item.get("source_id", "") for item in rasters if isinstance(item, dict))
    row["rasters.wms_layers"] = join_unique(item.get("wms_layer", "") for item in rasters if isinstance(item, dict))
    row["rasters.names"] = join_unique(item.get("name", "") for item in rasters if isinstance(item, dict))

    items = external_payload.get("items", []) if isinstance(external_payload.get("items"), list) else []
    row["external.count"] = str(len(items))
    row["external.ids"] = join_unique(item.get("id", "") for item in items if isinstance(item, dict))
    row["external.types"] = join_unique(item.get("type", "") for item in items if isinstance(item, dict))
    row["external.statuses"] = join_unique(item.get("status", "") for item in items if isinstance(item, dict))
    row["external.descriptions"] = join_unique(item.get("description", "") for item in items if isinstance(item, dict))
    row["external.created_at_list"] = join_unique(item.get("created_at", "") for item in items if isinstance(item, dict))
    row["external.updated_at_list"] = join_unique(item.get("updated_at", "") for item in items if isinstance(item, dict))
    row["external.errors"] = join_unique(
        error
        for item in items
        if isinstance(item, dict)
        for error in (item.get("errors") or [])
    )
    row["external.config_json"] = cell_text(
        [item.get("config", {}) for item in items if isinstance(item, dict)]
    )
    row["external.request_error"] = external_request_error
    row["external.json"] = cell_text(external_payload)

    found_external_meta_keys: set[str] = set()
    external_meta_values: dict[str, list[str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        meta_data = item.get("meta_data", {}) if isinstance(item.get("meta_data"), dict) else {}
        for key, value in meta_data.items():
            key_text = str(key)
            found_external_meta_keys.add(key_text)
            external_meta_values.setdefault(key_text, []).append(cell_text(value))

    external_meta_keys = selected_prefixed_keys(
        configured_fields=LDO_VELDEN,
        prefix="external.meta.",
        found_keys=found_external_meta_keys,
        include_all_found=NEEM_ALLE_VELDEN_MEE,
    )
    for key in external_meta_keys:
        row[f"external.meta.{key}"] = join_unique(external_meta_values.get(key, []))

    return row, found_scenario_keys, found_meta_keys, found_external_meta_keys


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()

    if not SCENARIO_IDS:
        raise SystemExit("Zet minstens één scenario-ID in SCENARIO_IDS.")

    token = get_token(required=True)
    session = make_session(token)
    run_dir = output_run_dir()

    overview_rows_raw: list[dict[str, str]] = []
    file_rows: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    found_scenario_keys: set[str] = set()
    found_meta_keys: set[str] = set()
    found_external_meta_keys: set[str] = set()
    external_items_total = 0

    scenario_ids = [int(scenario_id) for scenario_id in SCENARIO_IDS]
    if SMOKE_MODE:
        scenario_ids = scenario_ids[:SMOKE_MAX_SCENARIOS]
    total = len(scenario_ids)

    for index, scenario_id in enumerate(scenario_ids, start=1):
        print(f"Scenario {index}/{total}: {scenario_id}")
        scenario_dir = run_dir / str(scenario_id)
        if DOWNLOAD_BESTANDEN and not SMOKE_MODE:
            scenario_dir.mkdir(parents=True, exist_ok=True)

        try:
            scenario = fetch_scenario(session, BASE_URL, scenario_id)
        except Exception as exc:
            errors.append(
                {
                    "scenario_id": str(scenario_id),
                    "stage": "fetch_scenario",
                    "item_name": "",
                    "error": str(exc),
                }
            )
            if STOP_BIJ_EERSTE_FOUT:
                raise
            continue

        external_payload: dict[str, Any] = {"items": []}
        external_request_error = ""
        try:
            external_payload = fetch_external_processings(session, BASE_URL, scenario_id)
        except Exception as exc:
            external_request_error = str(exc)
            errors.append(
                {
                    "scenario_id": str(scenario_id),
                    "stage": "fetch_external_processings",
                    "item_name": "",
                    "error": str(exc),
                }
            )
            if STOP_BIJ_EERSTE_FOUT:
                raise

        external_items = external_payload.get("items", []) if isinstance(external_payload.get("items"), list) else []
        external_items_total += len(external_items)

        scenario_file_rows = build_file_rows(
            session=session,
            base_url=BASE_URL,
            scenario=scenario,
            scenario_dir=scenario_dir,
            errors=errors,
        )
        file_rows.extend(scenario_file_rows)

        overview_row, scenario_keys, scenario_meta_keys, scenario_external_meta_keys = build_overview_row(
            scenario=scenario,
            external_payload=external_payload,
            file_rows=scenario_file_rows,
            external_request_error=external_request_error,
        )
        overview_rows_raw.append(overview_row)
        found_scenario_keys.update(scenario_keys)
        found_meta_keys.update(scenario_meta_keys)
        found_external_meta_keys.update(scenario_external_meta_keys)

    overview_fieldnames = [field for field in LDO_VELDEN]
    if NEEM_ALLE_VELDEN_MEE:
        for key in sorted(found_scenario_keys, key=str.lower):
            field = f"scenario.{key}"
            if field not in overview_fieldnames:
                overview_fieldnames.append(field)
        for key in sorted(found_meta_keys, key=str.lower):
            field = f"meta.{key}"
            if field not in overview_fieldnames:
                overview_fieldnames.append(field)
        for key in sorted(found_external_meta_keys, key=str.lower):
            field = f"external.meta.{key}"
            if field not in overview_fieldnames:
                overview_fieldnames.append(field)

    overview_rows = [
        {field: row.get(field, "") for field in overview_fieldnames}
        for row in overview_rows_raw
    ]
    error_rows = [
        {
            "scenario_id": row.get("scenario_id", ""),
            "stage": row.get("stage", ""),
            "item_name": row.get("item_name", ""),
            "error": row.get("error", ""),
        }
        for row in errors
    ]

    workbook_path = run_dir / "batch_ldo_download_overzicht.xlsx"
    errors_csv = run_dir / "batch_ldo_download_errors.csv"
    summary_json = run_dir / "batch_ldo_download_summary.json"

    write_excel(workbook_path, overview_rows, overview_fieldnames, sheet_name="overzicht")
    write_csv(errors_csv, error_rows, ["scenario_id", "stage", "item_name", "error"])
    write_json(
        summary_json,
        {
            "scenario_ids": scenario_ids,
            "run_dir": str(run_dir),
            "scenario_count_requested": len(scenario_ids),
            "scenario_count_processed": len(overview_rows),
            "download_bestanden": DOWNLOAD_BESTANDEN and not SMOKE_MODE,
            "smoke_mode": SMOKE_MODE,
            "downloaded_files": sum(1 for row in file_rows if row.get("download_status") == "downloaded"),
            "file_download_errors": sum(1 for row in file_rows if row.get("download_status") == "error"),
            "external_items": external_items_total,
            "errors": len(error_rows),
            "outputs": {
                "workbook": str(workbook_path),
                "errors_csv": str(errors_csv),
                "summary_json": str(summary_json),
            },
        },
    )

    print("Batch overzicht (eerste scenario's):")
    print_table(
        overview_rows,
        [
            ("scenario.id", "scenario_id", 10),
            ("scenario.status", "status", 16),
            ("scenario.scenario_type", "scenario_type", 16),
            ("meta.scenarionaam", "scenarionaam", 30),
            ("files.count", "files", 6),
            ("external.count", "external", 8),
        ],
        MAX_CONSOLE_ROWS,
    )
    print("")
    print_json_block(
        "Batch download samenvatting:",
        {
            "scenario_count_requested": len(scenario_ids),
            "scenario_count_processed": len(overview_rows),
            "download_bestanden": DOWNLOAD_BESTANDEN and not SMOKE_MODE,
            "smoke_mode": SMOKE_MODE,
            "downloaded_files": sum(1 for row in file_rows if row.get("download_status") == "downloaded"),
            "file_download_errors": sum(1 for row in file_rows if row.get("download_status") == "error"),
            "external_items": external_items_total,
            "errors": len(error_rows),
            "run_dir": str(run_dir),
        },
    )
    print(f"Wrote: {workbook_path}")
    print(f"Wrote: {summary_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
