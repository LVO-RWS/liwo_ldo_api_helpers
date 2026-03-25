#!/usr/bin/env python3
"""Vind LIWO scenario's terug in LDO en maak bruikbare overzichten.

Dit script doet vijf dingen:
1. haalt actuele LIWO scenario-layers op via WMS GetCapabilities
2. haalt publieke en niet-publieke LDO scenario's op
3. koppelt LIWO IDs aan LDO IDs op exact scenario-id
4. markeert LIWO scenario's die in niet-publiek LDO al op archief/afkeur kunnen wijzen
5. schrijft duidelijke CSV- en Excel-bestanden weg voor verdere analyse

Benodigd:
- een geldig LDO_TOKEN in .env of in je environment
- toegang tot de LIWO WMS en de LDO API

Output in output/ldo/:
- alle_liwo_scenario_layers_gevonden.csv
- alle_liwo_scenario_layers_gevonden.xlsx
- liwo_to_ldo_mapping.csv
- liwo_to_ldo_mapping.xlsx
- liwo_to_ldo_missing.csv
- liwo_to_ldo_missing.xlsx
- liwo_met_niet_publiek_ldo.csv
- liwo_met_niet_publiek_ldo.xlsx
- liwo_ldo_overzicht.csv
- liwo_ldo_overzicht.xlsx
- liwo_ldo_overzicht_incl_externalprocessings_meta.csv
- liwo_ldo_overzicht_incl_externalprocessings_meta.xlsx
- liwo_to_ldo_summary.json
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.etree import ElementTree as ET

import requests

from _ldo_common import (
    get_base,
    get_liwo_base,
    get_token,
    iter_scenarios,
    load_env_fallback,
    make_session,
    output_file,
    print_json_block,
    print_table,
    write_csv,
    write_excel,
    write_json,
)

# Instellingen
LIWO_TIMEOUT_SEC = 30
LDO_PAGINA_GROOTTE = 200
MAX_AANTAL_LDO_SCENARIOS = 0  # 0 = alles
DOEL_WORKSPACES = ["LIWO_Primair", "LIWO_Regionaal", "LIWO_RegionaalSysteem"]
EXTERNAL_PROCESSINGS_MAX_WORKERS = 12
EXTERNAL_PROCESSINGS_TIMEOUT_SEC = 60
MAX_CONSOLE_ROWS = 20
WMS_NS = {"wms": "http://www.opengis.net/wms"}
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"
SMOKE_MAX_AANTAL_LDO_SCENARIOS = 50
SMOKE_MAX_AANTAL_LIWO_ROWS = 10
SMOKE_MAX_EXTERNAL_IDS = 10
SMOKE_DOEL_WORKSPACES = ["LIWO_Primair"]
SMOKE_LIWO_ROWS = [
    {
        "workspace": "LIWO_Primair",
        "liwo_id": "310",
        "liwo_layer_name": "LIWO_Primair:scenario_310",
        "liwo_layer_title": "scenario_310",
        "liwo_layer_abstract": "",
        "liwo_layer_crs_list": "",
        "liwo_layer_style_names": "",
    },
    {
        "workspace": "LIWO_Primair",
        "liwo_id": "317",
        "liwo_layer_name": "LIWO_Primair:scenario_317",
        "liwo_layer_title": "scenario_317",
        "liwo_layer_abstract": "",
        "liwo_layer_crs_list": "",
        "liwo_layer_style_names": "",
    },
]

LIWO_FIELDNAMES = [
    "workspace",
    "liwo_id",
    "liwo_layer_name",
    "liwo_layer_title",
    "liwo_layer_abstract",
    # Tijdelijk uitgezet:
    # "liwo_layer_queryable",
    # "liwo_layer_opaque",
    # "liwo_layer_keyword_list",
    "liwo_layer_crs_list",
    # "liwo_layer_bbox_crs84_minx",
    # "liwo_layer_bbox_crs84_miny",
    # "liwo_layer_bbox_crs84_maxx",
    # "liwo_layer_bbox_crs84_maxy",
    # "liwo_layer_bbox_epsg28992_minx",
    # "liwo_layer_bbox_epsg28992_miny",
    # "liwo_layer_bbox_epsg28992_maxx",
    # "liwo_layer_bbox_epsg28992_maxy",
    # "liwo_layer_geo_west_bound_longitude",
    # "liwo_layer_geo_east_bound_longitude",
    # "liwo_layer_geo_south_bound_latitude",
    # "liwo_layer_geo_north_bound_latitude",
    "liwo_layer_style_names",
]

OVERVIEW_FIXED_FIELDNAMES = LIWO_FIELDNAMES + [
    "gevonden_in_ldo",
    "ldo_match_scope",
    "match_method",
    "ldo_niet_publiek_id",
    "ldo_niet_publiek_name",
    "ldo_niet_publiek_status",
    "ldo_id",
    "ldo_tenant",
    "ldo_name",
    "ldo_area_name",
    "ldo_status",
    "ldo_scenario_type",
    "ldo_inundation_source",
    "ldo_meta_version",
    "ldo_excel_import_id",
    "ldo_breach_growth_start",
    "ldo_created_at",
    "ldo_created_by_id",
    "ldo_created_by_name",
    "ldo_updated_at",
    "ldo_updated_by_id",
    "ldo_updated_by_name",
    "ldo_errors",
    "ldo_breach_count",
    "ldo_breach_lats",
    "ldo_breach_lons",
    "ldo_raster_count",
    # Tijdelijk uitgezet:
    # "ldo_raster_ids",
    # "ldo_raster_names",
    # "ldo_raster_source_ids",
    # "ldo_raster_types",
    # "ldo_raster_wms_layers",
    "ldo_file_count",
    "ldo_file_names",
    "ldo_file_types",
    # "ldo_file_is_user_input",
    "ldo_file_created_at_list",
    "ldo_file_sizes",
    # "ldo_file_etags",
    "ldo_file_total_size",
]

EXTERNAL_FIXED_FIELDNAMES = [
    "external_processings_count",
    "external_processings_ids",
    "external_processings_types",
    "external_processings_statuses",
    "external_processings_created_at_list",
    "external_processings_updated_at_list",
    "external_processings_descriptions",
    "external_processings_errors",
    "external_processings_config_json",
    "external_processings_request_error",
]


def get_wms_text(parent, path: str) -> str:
    """Return text from a nested WMS element.

    Parameters
    ----------
    parent : Any
        Parent XML element.
    path : str
        Target path for this operation.

    Returns
    -------
    str
        Wms text.
    """
    node = parent.find(path, WMS_NS)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def normalize_column_name(value: str) -> str:
    """Normalize column name.

    Parameters
    ----------
    value : str
        Value to inspect or format.

    Returns
    -------
    str
        Text result.
    """
    text = re.sub(r"[^0-9a-zA-Z]+", "_", str(value).strip().lower())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "veld"


def cell_text(value) -> str:
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
    if isinstance(value, (dict, list)):
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


def haal_liwo_scenario_lagen_op(
    liwo_base_url: str,
    doel_workspaces: list[str],
) -> list[dict[str, str]]:
    """Fetch LIWO scenario layers for the selected workspaces.

    Parameters
    ----------
    liwo_base_url : str
        Base URL for the LIWO API.
    doel_workspaces : list[str]
        Workspaces that should be scanned.

    Returns
    -------
    list[dict[str, str]]
        Collected items.
    """
    params = {"service": "WMS", "request": "GetCapabilities", "version": "1.3.0"}
    wms_url = (
        f"{liwo_base_url.rstrip('/')}/{doel_workspaces[0]}/wms"
        if len(doel_workspaces) == 1
        else f"{liwo_base_url.rstrip('/')}/wms"
    )

    try:
        response = requests.get(wms_url, params=params, timeout=LIWO_TIMEOUT_SEC)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SystemExit(
            f"LIWO scenario-layers ophalen mislukte via {wms_url}: {exc}"
        ) from exc

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise SystemExit("LIWO gaf geen geldige XML terug.") from exc

    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for layer in root.findall(".//wms:Layer", WMS_NS):
        layer_name = get_wms_text(layer, "wms:Name")
        if ":" in layer_name:
            workspace, child_name = layer_name.split(":", 1)
            if workspace not in doel_workspaces:
                continue
        elif len(doel_workspaces) == 1 and re.fullmatch(r"scenario_\d+", layer_name):
            workspace = doel_workspaces[0]
            child_name = layer_name
            layer_name = f"{workspace}:{child_name}"
        else:
            continue

        match = re.fullmatch(r"scenario_(\d+)", child_name)
        if not match:
            continue

        liwo_id = match.group(1)
        key = (workspace, liwo_id)
        if key in seen:
            continue
        seen.add(key)

        styles = [
            get_wms_text(style, "wms:Name")
            for style in layer.findall("wms:Style", WMS_NS)
            if get_wms_text(style, "wms:Name")
        ]
        crs_values = [
            node.text.strip()
            for node in layer.findall("wms:CRS", WMS_NS)
            if node.text and node.text.strip()
        ]

        row = {
            "workspace": workspace,
            "liwo_id": liwo_id,
            "liwo_layer_name": layer_name,
            "liwo_layer_title": get_wms_text(layer, "wms:Title"),
            "liwo_layer_abstract": get_wms_text(layer, "wms:Abstract"),
            # Tijdelijk niet meenemen in output:
            # "liwo_layer_queryable": layer.attrib.get("queryable", "").strip(),
            # "liwo_layer_opaque": layer.attrib.get("opaque", "").strip(),
            # "liwo_layer_keyword_list": join_unique(keywords),
            # "liwo_layer_geo_west_bound_longitude": ...,
            # "liwo_layer_geo_east_bound_longitude": ...,
            # "liwo_layer_geo_south_bound_latitude": ...,
            # "liwo_layer_geo_north_bound_latitude": ...,
            "liwo_layer_crs_list": join_unique(crs_values),
            "liwo_layer_style_names": join_unique(styles),
        }
        rows.append(row)

    rows.sort(key=lambda row: (row["workspace"], int(row["liwo_id"])))
    return rows


def flatten_ldo_scenario(scenario: dict) -> tuple[dict[str, str], set[str]]:
    """Flatten one LDO scenario into a comparison row.

    Parameters
    ----------
    scenario : dict
        Scenario payload to inspect.

    Returns
    -------
    tuple[dict[str, str], set[str]]
        Tuple with the requested values.
    """
    created_by = scenario.get("created_by", {}) if isinstance(scenario, dict) else {}
    updated_by = scenario.get("updated_by", {}) if isinstance(scenario, dict) else {}
    meta = scenario.get("meta", {}) if isinstance(scenario, dict) else {}
    breaches = scenario.get("breaches", []) if isinstance(scenario, dict) else []
    rasters = scenario.get("rasters", []) if isinstance(scenario, dict) else []
    files = scenario.get("files", {}) if isinstance(scenario, dict) else {}
    errors = scenario.get("errors", []) if isinstance(scenario, dict) else []

    if not isinstance(created_by, dict):
        created_by = {}
    if not isinstance(updated_by, dict):
        updated_by = {}
    if not isinstance(meta, dict):
        meta = {}
    if not isinstance(breaches, list):
        breaches = []
    if not isinstance(rasters, list):
        rasters = []
    if not isinstance(files, dict):
        files = {}
    if not isinstance(errors, list):
        errors = []

    file_sizes: list[str] = []
    file_created_at: list[str] = []
    file_types: list[str] = []
    total_size = 0
    for file_name, file_info in files.items():
        if not isinstance(file_info, dict):
            continue
        nested = file_info.get("file", {})
        if not isinstance(nested, dict):
            nested = {}
        file_types.append(file_info.get("type"))
        file_created_at.append(nested.get("created_at"))
        file_sizes.append(nested.get("size"))
        try:
            total_size += int(nested.get("size", 0) or 0)
        except Exception:
            continue

    row = {
        "ldo_id": cell_text(scenario.get("id")),
        "ldo_tenant": cell_text(scenario.get("tenant")),
        "ldo_name": cell_text(scenario.get("name")),
        "ldo_area_name": cell_text(scenario.get("area_name")),
        "ldo_status": cell_text(scenario.get("status")),
        "ldo_scenario_type": cell_text(scenario.get("scenario_type")),
        "ldo_inundation_source": cell_text(scenario.get("inundation_source")),
        "ldo_meta_version": cell_text(scenario.get("meta_version")),
        "ldo_excel_import_id": cell_text(scenario.get("excel_import_id")),
        "ldo_breach_growth_start": cell_text(scenario.get("breach_growth_start")),
        "ldo_created_at": cell_text(scenario.get("created_at")),
        "ldo_created_by_id": cell_text(created_by.get("id")),
        "ldo_created_by_name": cell_text(created_by.get("name")),
        "ldo_updated_at": cell_text(scenario.get("updated_at")),
        "ldo_updated_by_id": cell_text(updated_by.get("id")),
        "ldo_updated_by_name": cell_text(updated_by.get("name")),
        "ldo_errors": join_unique(errors),
        "ldo_breach_count": cell_text(len(breaches)),
        "ldo_breach_lats": join_unique(
            breach.get("lat") for breach in breaches if isinstance(breach, dict)
        ),
        "ldo_breach_lons": join_unique(
            breach.get("lon") for breach in breaches if isinstance(breach, dict)
        ),
        "ldo_raster_count": cell_text(len(rasters)),
        # Tijdelijk niet meenemen in output:
        # "ldo_raster_ids": ...,
        # "ldo_raster_names": ...,
        # "ldo_raster_source_ids": ...,
        # "ldo_raster_types": ...,
        # "ldo_raster_wms_layers": ...,
        "ldo_file_count": cell_text(len(files)),
        "ldo_file_names": join_unique(files.keys()),
        "ldo_file_types": join_unique(file_types),
        # "ldo_file_is_user_input": ...,
        "ldo_file_created_at_list": join_unique(file_created_at),
        "ldo_file_sizes": join_unique(file_sizes),
        # "ldo_file_etags": ...,
        "ldo_file_total_size": cell_text(total_size),
    }

    meta_columns: set[str] = set()
    for key, value in meta.items():
        column = f"ldo_meta_{normalize_column_name(key)}"
        row[column] = cell_text(value)
        meta_columns.add(column)

    return row, meta_columns


def haal_ldo_scenarios_op(
    session: requests.Session,
    ldo_base_url: str,
    mode_public: bool,
    max_aantal_ldo_scenarios: int,
) -> tuple[dict[str, dict[str, str]], int, set[str]]:
    """Fetch LDO scenarios for comparison.

    Parameters
    ----------
    session : requests.Session
        Authenticated requests session.
    ldo_base_url : str
        Base URL for the LDO API.
    mode_public : bool
        Whether to request only public scenarios.
    max_aantal_ldo_scenarios : int
        Maximum number of LDO scenarios to scan. Use `0` for all.

    Returns
    -------
    tuple[dict[str, dict[str, str]], int, set[str]]
        Tuple with the requested values.
    """
    by_ldo_id: dict[str, dict[str, str]] = {}
    ldo_rows_scanned = 0
    meta_columns: set[str] = set()

    for scenario in iter_scenarios(
        session=session,
        base=ldo_base_url,
        limit=LDO_PAGINA_GROOTTE,
        max_scenarios=max_aantal_ldo_scenarios,
        mode_public=mode_public,
    ):
        ldo_id = str(scenario.get("id", "")).strip()
        if not ldo_id:
            continue

        ldo_rows_scanned += 1
        row, scenario_meta_columns = flatten_ldo_scenario(scenario)
        by_ldo_id[ldo_id] = row
        meta_columns.update(scenario_meta_columns)

    return by_ldo_id, ldo_rows_scanned, meta_columns


def maak_overzicht_rows(
    liwo_rows: list[dict[str, str]],
    by_public_ldo_id: dict[str, dict[str, str]],
    by_nonpublic_ldo_id: dict[str, dict[str, str]],
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    """Build comparison rows between LIWO and LDO scenarios.

    Parameters
    ----------
    liwo_rows : list[dict[str, str]]
        LIWO rows used as input for the comparison.
    by_public_ldo_id : dict[str, dict[str, str]]
        Lookup with public LDO rows keyed by id.
    by_nonpublic_ldo_id : dict[str, dict[str, str]]
        Lookup with non-public LDO rows keyed by id.

    Returns
    -------
    tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]
        Tuple with the requested values.
    """
    overview_rows: list[dict[str, str]] = []
    mapped_rows: list[dict[str, str]] = []
    missing_rows: list[dict[str, str]] = []
    nonpublic_rows: list[dict[str, str]] = []

    for liwo_row in liwo_rows:
        row = dict(liwo_row)
        liwo_id = liwo_row["liwo_id"]
        public_ldo_row = by_public_ldo_id.get(liwo_id)
        nonpublic_ldo_row = by_nonpublic_ldo_id.get(liwo_id)
        matched_ldo_row = public_ldo_row or nonpublic_ldo_row
        nonpublic_status = nonpublic_ldo_row.get("ldo_status", "") if nonpublic_ldo_row else ""
        if public_ldo_row and nonpublic_ldo_row:
            match_scope = "publiek_en_niet_publiek"
        elif public_ldo_row:
            match_scope = "publiek"
        elif nonpublic_ldo_row:
            match_scope = "niet_publiek"
        else:
            match_scope = ""

        if matched_ldo_row:
            row["gevonden_in_ldo"] = "ja"
            row["ldo_match_scope"] = match_scope
            row["match_method"] = "scenario.id"
            row.update(matched_ldo_row)
            row["ldo_niet_publiek_id"] = (
                nonpublic_ldo_row.get("ldo_id", "") if nonpublic_ldo_row else ""
            )
            row["ldo_niet_publiek_name"] = (
                nonpublic_ldo_row.get("ldo_name", "") if nonpublic_ldo_row else ""
            )
            row["ldo_niet_publiek_status"] = nonpublic_status
            mapped_rows.append(
                {
                    "workspace": liwo_row["workspace"],
                    "liwo_id": liwo_id,
                    "liwo_layer_name": liwo_row["liwo_layer_name"],
                    "liwo_layer_title": liwo_row["liwo_layer_title"],
                    "ldo_id": matched_ldo_row.get("ldo_id", ""),
                    "ldo_name": matched_ldo_row.get("ldo_name", ""),
                    "ldo_status": matched_ldo_row.get("ldo_status", ""),
                    "ldo_scenario_type": matched_ldo_row.get("ldo_scenario_type", ""),
                    "ldo_match_scope": row["ldo_match_scope"],
                    "ldo_niet_publiek_status": row["ldo_niet_publiek_status"],
                    "match_method": "scenario.id",
                }
            )
            if nonpublic_ldo_row:
                nonpublic_rows.append(dict(row))
        else:
            row["gevonden_in_ldo"] = "nee"
            row["ldo_match_scope"] = ""
            row["match_method"] = ""
            row["ldo_niet_publiek_id"] = ""
            row["ldo_niet_publiek_name"] = ""
            row["ldo_niet_publiek_status"] = ""
            missing_rows.append(
                {
                    "workspace": liwo_row["workspace"],
                    "liwo_id": liwo_id,
                    "liwo_layer_name": liwo_row["liwo_layer_name"],
                    "liwo_layer_title": liwo_row["liwo_layer_title"],
                }
            )

        overview_rows.append(row)

    return overview_rows, mapped_rows, missing_rows, nonpublic_rows


def flatten_external_processings(
    payload: dict,
) -> tuple[dict[str, str], set[str]]:
    """Flatten external processings into output rows.

    Parameters
    ----------
    payload : dict
        Payload to write or print.

    Returns
    -------
    tuple[dict[str, str], set[str]]
        Tuple with the requested values.
    """
    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        items = []

    rows = {
        "external_processings_count": cell_text(len(items)),
        "external_processings_ids": join_unique(
            item.get("id") for item in items if isinstance(item, dict)
        ),
        "external_processings_types": join_unique(
            item.get("type") for item in items if isinstance(item, dict)
        ),
        "external_processings_statuses": join_unique(
            item.get("status") for item in items if isinstance(item, dict)
        ),
        "external_processings_created_at_list": join_unique(
            item.get("created_at") for item in items if isinstance(item, dict)
        ),
        "external_processings_updated_at_list": join_unique(
            item.get("updated_at") for item in items if isinstance(item, dict)
        ),
        "external_processings_descriptions": join_unique(
            item.get("description") for item in items if isinstance(item, dict)
        ),
        "external_processings_errors": join_unique(
            error
            for item in items
            if isinstance(item, dict)
            for error in (item.get("errors") or [])
        ),
        "external_processings_config_json": cell_text(
            [item.get("config", {}) for item in items if isinstance(item, dict)]
        ),
        "external_processings_request_error": "",
    }

    meta_columns: set[str] = set()
    meta_values: dict[str, list[str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        meta_data = item.get("meta_data", {})
        if not isinstance(meta_data, dict):
            continue
        for key, value in meta_data.items():
            column = f"external_meta_{normalize_column_name(key)}"
            meta_columns.add(column)
            meta_values.setdefault(column, []).append(cell_text(value))

    for column, values in meta_values.items():
        rows[column] = join_unique(values)

    return rows, meta_columns


def fetch_external_processing_row(
    ldo_id: str,
    ldo_base_url: str,
    headers: dict[str, str],
) -> tuple[str, dict[str, str], set[str]]:
    """Fetch and flatten external processings for one LDO scenario.

    Parameters
    ----------
    ldo_id : str
        LDO scenario identifier.
    ldo_base_url : str
        Base URL for the LDO API.
    headers : dict[str, str]
        HTTP headers used for the request.

    Returns
    -------
    tuple[str, dict[str, str], set[str]]
        Tuple with the requested values.
    """
    url = f"{ldo_base_url.rstrip('/')}/scenarios/{ldo_id}/external-processings"
    try:
        response = requests.get(url, headers=headers, timeout=EXTERNAL_PROCESSINGS_TIMEOUT_SEC)
        response.raise_for_status()
        payload = response.json()
        row, meta_columns = flatten_external_processings(payload)
        return ldo_id, row, meta_columns
    except Exception as exc:
        return (
            ldo_id,
            {
                "external_processings_count": "",
                "external_processings_ids": "",
                "external_processings_types": "",
                "external_processings_statuses": "",
                "external_processings_created_at_list": "",
                "external_processings_updated_at_list": "",
                "external_processings_descriptions": "",
                "external_processings_errors": "",
                "external_processings_config_json": "",
                "external_processings_request_error": str(exc),
            },
            set(),
        )


def haal_external_processings_op(
    matched_ldo_ids: list[str],
    token: str,
    ldo_base_url: str,
) -> tuple[dict[str, dict[str, str]], set[str]]:
    """Fetch external processings for the matched LDO scenarios.

    Parameters
    ----------
    matched_ldo_ids : list[str]
        Matched LDO scenario identifiers.
    token : str
        Bearer token used for authenticated requests.
    ldo_base_url : str
        Base URL for the LDO API.

    Returns
    -------
    tuple[dict[str, dict[str, str]], set[str]]
        Tuple with the requested values.
    """
    headers = {"accept": "application/json", "authorization": f"Bearer {token}"}
    results: dict[str, dict[str, str]] = {}
    meta_columns: set[str] = set()
    total = len(matched_ldo_ids)

    if not matched_ldo_ids:
        return results, meta_columns

    with ThreadPoolExecutor(max_workers=EXTERNAL_PROCESSINGS_MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                fetch_external_processing_row,
                ldo_id,
                ldo_base_url,
                headers,
            ): ldo_id
            for ldo_id in matched_ldo_ids
        }
        done = 0
        for future in as_completed(futures):
            ldo_id, row, row_meta_columns = future.result()
            results[ldo_id] = row
            meta_columns.update(row_meta_columns)
            done += 1
            if done % 250 == 0 or done == total:
                print(f"External-processings opgehaald: {done}/{total}")

    return results, meta_columns


def maak_overzicht_met_external_rows(
    overview_rows: list[dict[str, str]],
    external_by_ldo_id: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    """Build overview rows enriched with external processings.

    Parameters
    ----------
    overview_rows : list[dict[str, str]]
        Overview rows for the report.
    external_by_ldo_id : dict[str, dict[str, str]]
        Lookup with external processings keyed by LDO id.

    Returns
    -------
    list[dict[str, str]]
        Collected output rows.
    """
    rows: list[dict[str, str]] = []
    for overview_row in overview_rows:
        row = dict(overview_row)
        ldo_id = overview_row.get("ldo_id", "")
        if ldo_id and ldo_id in external_by_ldo_id:
            row.update(external_by_ldo_id[ldo_id])
        rows.append(row)
    return rows


def schrijf_outputbestanden(
    liwo_rows: list[dict[str, str]],
    overview_rows: list[dict[str, str]],
    overview_ext_rows: list[dict[str, str]],
    mapped_rows: list[dict[str, str]],
    missing_rows: list[dict[str, str]],
    nonpublic_rows: list[dict[str, str]],
    public_ldo_rows_scanned: int,
    nonpublic_ldo_rows_scanned: int,
    ldo_meta_columns: set[str],
    external_meta_columns: set[str],
    ldo_base_url: str,
    liwo_base_url: str,
    doel_workspaces: list[str],
) -> tuple:
    """Write the output files for this script.

    Parameters
    ----------
    liwo_rows : list[dict[str, str]]
        LIWO rows used as input for the comparison.
    overview_rows : list[dict[str, str]]
        Overview rows for the report.
    overview_ext_rows : list[dict[str, str]]
        Overview rows enriched with external processings.
    mapped_rows : list[dict[str, str]]
        Rows that could be mapped to LDO scenarios.
    missing_rows : list[dict[str, str]]
        Rows without a matching LDO scenario.
    nonpublic_rows : list[dict[str, str]]
        Rows for matched non-public LDO scenarios.
    public_ldo_rows_scanned : int
        Number of public LDO rows that were scanned.
    nonpublic_ldo_rows_scanned : int
        Number of non-public LDO rows that were scanned.
    ldo_meta_columns : set[str]
        Selected metadata columns for LDO rows.
    external_meta_columns : set[str]
        Selected metadata columns for external processings.
    ldo_base_url : str
        Base URL for the LDO API.
    liwo_base_url : str
        Base URL for the LIWO API.
    doel_workspaces : list[str]
        Workspaces that should be scanned.

    Returns
    -------
    tuple
        Tuple with the requested values.
    """
    liwo_csv = output_file("alle_liwo_scenario_layers_gevonden.csv")
    liwo_xlsx = output_file("alle_liwo_scenario_layers_gevonden.xlsx")
    overview_csv = output_file("liwo_ldo_overzicht.csv")
    overview_xlsx = output_file("liwo_ldo_overzicht.xlsx")
    overview_ext_csv = output_file("liwo_ldo_overzicht_incl_externalprocessings_meta.csv")
    overview_ext_xlsx = output_file(
        "liwo_ldo_overzicht_incl_externalprocessings_meta.xlsx"
    )
    map_csv = output_file("liwo_to_ldo_mapping.csv")
    map_xlsx = output_file("liwo_to_ldo_mapping.xlsx")
    missing_csv = output_file("liwo_to_ldo_missing.csv")
    missing_xlsx = output_file("liwo_to_ldo_missing.xlsx")
    nonpublic_csv = output_file("liwo_met_niet_publiek_ldo.csv")
    nonpublic_xlsx = output_file("liwo_met_niet_publiek_ldo.xlsx")
    summary_json = output_file("liwo_to_ldo_summary.json")

    overview_fieldnames = OVERVIEW_FIXED_FIELDNAMES + sorted(ldo_meta_columns)
    overview_ext_fieldnames = overview_fieldnames + EXTERNAL_FIXED_FIELDNAMES + sorted(
        external_meta_columns
    )
    map_fieldnames = [
        "workspace",
        "liwo_id",
        "liwo_layer_name",
        "liwo_layer_title",
        "ldo_id",
        "ldo_name",
        "ldo_status",
        "ldo_scenario_type",
        "ldo_match_scope",
        "ldo_niet_publiek_status",
        "match_method",
    ]
    missing_fieldnames = ["workspace", "liwo_id", "liwo_layer_name", "liwo_layer_title"]
    nonpublic_fieldnames = overview_fieldnames

    write_csv(liwo_csv, liwo_rows, LIWO_FIELDNAMES)
    write_excel(liwo_xlsx, liwo_rows, LIWO_FIELDNAMES, "Alle LIWO lagen")
    write_csv(map_csv, mapped_rows, map_fieldnames)
    write_excel(map_xlsx, mapped_rows, map_fieldnames, "Mapping")
    write_csv(missing_csv, missing_rows, missing_fieldnames)
    write_excel(missing_xlsx, missing_rows, missing_fieldnames, "Niet gevonden")
    write_csv(nonpublic_csv, nonpublic_rows, nonpublic_fieldnames)
    write_excel(
        nonpublic_xlsx,
        nonpublic_rows,
        nonpublic_fieldnames,
        "Niet publiek LDO",
    )
    write_csv(overview_csv, overview_rows, overview_fieldnames)
    write_excel(overview_xlsx, overview_rows, overview_fieldnames, "LIWO en LDO overzicht")
    write_csv(overview_ext_csv, overview_ext_rows, overview_ext_fieldnames)
    write_excel(
        overview_ext_xlsx,
        overview_ext_rows,
        overview_ext_fieldnames,
        "Overzicht incl external meta",
    )
    write_json(
        summary_json,
        {
            "liwo_rows": len(liwo_rows),
            "ldo_public_rows_scanned": public_ldo_rows_scanned,
            "ldo_nonpublic_rows_scanned": nonpublic_ldo_rows_scanned,
            "mapped": len(mapped_rows),
            "missing": len(missing_rows),
            "niet_publieke_ldo_matches": len(nonpublic_rows),
            "niet_publieke_ldo_status_counts": dict(
                sorted(Counter(row["ldo_niet_publiek_status"] for row in nonpublic_rows).items())
            ),
            "liwo_base_url": liwo_base_url,
            "liwo_wms_url": f"{liwo_base_url.rstrip('/')}/wms",
            "ldo_base_url": ldo_base_url,
            "doel_workspaces": doel_workspaces,
            "match_method": "scenario.id",
            "match_pct_of_liwo": round((100.0 * len(mapped_rows) / len(liwo_rows)), 2)
            if liwo_rows
            else 0.0,
            "outputs": {
                "alle_liwo_scenario_layers_gevonden_csv": str(liwo_csv),
                "alle_liwo_scenario_layers_gevonden_xlsx": str(liwo_xlsx),
                "liwo_to_ldo_mapping_csv": str(map_csv),
                "liwo_to_ldo_mapping_xlsx": str(map_xlsx),
                "liwo_to_ldo_missing_csv": str(missing_csv),
                "liwo_to_ldo_missing_xlsx": str(missing_xlsx),
                "liwo_met_niet_publiek_ldo_csv": str(nonpublic_csv),
                "liwo_met_niet_publiek_ldo_xlsx": str(nonpublic_xlsx),
                "liwo_ldo_overzicht_csv": str(overview_csv),
                "liwo_ldo_overzicht_xlsx": str(overview_xlsx),
                "liwo_ldo_overzicht_incl_externalprocessings_meta_csv": str(
                    overview_ext_csv
                ),
                "liwo_ldo_overzicht_incl_externalprocessings_meta_xlsx": str(
                    overview_ext_xlsx
                ),
            },
        },
    )

    return (
        liwo_csv,
        liwo_xlsx,
        overview_csv,
        overview_xlsx,
        overview_ext_csv,
        overview_ext_xlsx,
        map_csv,
        map_xlsx,
        missing_csv,
        missing_xlsx,
        nonpublic_csv,
        nonpublic_xlsx,
        summary_json,
    )


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()
    token = get_token(required=True)
    ldo_base_url = get_base()
    liwo_base_url = get_liwo_base()
    session = make_session(token)
    doel_workspaces = SMOKE_DOEL_WORKSPACES if SMOKE_MODE else DOEL_WORKSPACES
    max_aantal_ldo_scenarios = (
        SMOKE_MAX_AANTAL_LDO_SCENARIOS if SMOKE_MODE else MAX_AANTAL_LDO_SCENARIOS
    )

    if SMOKE_MODE:
        print(
            "Smoke mode actief: "
            f"workspaces={doel_workspaces}, "
            f"max_ldo_scenarios={max_aantal_ldo_scenarios}, "
            f"max_liwo_rows={SMOKE_MAX_AANTAL_LIWO_ROWS}, "
            f"max_external_ids={SMOKE_MAX_EXTERNAL_IDS}"
        )

    print("Stap 1/4: LIWO scenario-layers ophalen...")
    if SMOKE_MODE:
        liwo_rows = SMOKE_LIWO_ROWS[:SMOKE_MAX_AANTAL_LIWO_ROWS]
    else:
        liwo_rows = haal_liwo_scenario_lagen_op(liwo_base_url, doel_workspaces)
    print(f"Gevonden LIWO scenario-layers: {len(liwo_rows)}")

    print("Stap 2/4: publieke en niet-publieke LDO scenario's scannen...")
    by_public_ldo_id, public_ldo_rows_scanned, public_ldo_meta_columns = haal_ldo_scenarios_op(
        session=session,
        ldo_base_url=ldo_base_url,
        mode_public=True,
        max_aantal_ldo_scenarios=max_aantal_ldo_scenarios,
    )
    by_nonpublic_ldo_id, nonpublic_ldo_rows_scanned, nonpublic_ldo_meta_columns = (
        haal_ldo_scenarios_op(
            session=session,
            ldo_base_url=ldo_base_url,
            mode_public=False,
            max_aantal_ldo_scenarios=max_aantal_ldo_scenarios,
        )
    )
    ldo_meta_columns = public_ldo_meta_columns | nonpublic_ldo_meta_columns
    print(f"Gescannde publieke LDO scenario's: {public_ldo_rows_scanned}")
    print(f"Gescannde niet-publieke LDO scenario's: {nonpublic_ldo_rows_scanned}")

    print("Stap 3/4: LIWO en LDO aan elkaar koppelen...")
    overview_rows, mapped_rows, missing_rows, nonpublic_rows = maak_overzicht_rows(
        liwo_rows=liwo_rows,
        by_public_ldo_id=by_public_ldo_id,
        by_nonpublic_ldo_id=by_nonpublic_ldo_id,
    )
    print(f"Gekoppeld: {len(mapped_rows)}")
    print(f"Niet gevonden: {len(missing_rows)}")
    print(f"Met niet-publieke LDO-match: {len(nonpublic_rows)}")

    print("Stap 4/4: external-processings metadata ophalen...")
    matched_ldo_ids = [row["ldo_id"] for row in mapped_rows if row.get("ldo_id")]
    if SMOKE_MODE:
        matched_ldo_ids = matched_ldo_ids[:SMOKE_MAX_EXTERNAL_IDS]
    external_by_ldo_id, external_meta_columns = haal_external_processings_op(
        matched_ldo_ids=matched_ldo_ids,
        token=token,
        ldo_base_url=ldo_base_url,
    )
    overview_ext_rows = maak_overzicht_met_external_rows(
        overview_rows=overview_rows,
        external_by_ldo_id=external_by_ldo_id,
    )

    (
        liwo_csv,
        liwo_xlsx,
        overview_csv,
        overview_xlsx,
        overview_ext_csv,
        overview_ext_xlsx,
        map_csv,
        map_xlsx,
        missing_csv,
        missing_xlsx,
        nonpublic_csv,
        nonpublic_xlsx,
        summary_json,
    ) = schrijf_outputbestanden(
        liwo_rows=liwo_rows,
        overview_rows=overview_rows,
        overview_ext_rows=overview_ext_rows,
        mapped_rows=mapped_rows,
        missing_rows=missing_rows,
        nonpublic_rows=nonpublic_rows,
        public_ldo_rows_scanned=public_ldo_rows_scanned,
        nonpublic_ldo_rows_scanned=nonpublic_ldo_rows_scanned,
        ldo_meta_columns=ldo_meta_columns,
        external_meta_columns=external_meta_columns,
        ldo_base_url=ldo_base_url,
        liwo_base_url=liwo_base_url,
        doel_workspaces=doel_workspaces,
    )

    print("")
    print("Voorbeeld overzichtsrijen:")
    print_table(
        overview_rows,
        [
            ("workspace", "workspace", 22),
            ("liwo_id", "liwo_id", 10),
            ("liwo_layer_title", "liwo_title", 14),
            ("gevonden_in_ldo", "in_ldo", 8),
            ("ldo_name", "ldo_name", 32),
            ("ldo_scenario_type", "scenario_type", 14),
            ("ldo_meta_gebiedsnaam", "gebiedsnaam", 24),
            ("ldo_meta_naam_doorbraaklocatie", "doorbraaklocatie", 24),
        ],
        MAX_CONSOLE_ROWS,
    )
    print("")
    print("Voorbeeld niet gevonden LIWO IDs:")
    print_table(
        missing_rows,
        [
            ("workspace", "workspace", 22),
            ("liwo_id", "liwo_id", 10),
            ("liwo_layer_name", "layer_name", 28),
        ],
        MAX_CONSOLE_ROWS,
    )
    print("")
    print("Voorbeeld LIWO scenario's met niet-publieke LDO-match:")
    print_table(
        nonpublic_rows,
        [
            ("workspace", "workspace", 22),
            ("liwo_id", "liwo_id", 10),
            ("ldo_niet_publiek_status", "niet_pub_status", 18),
            ("ldo_niet_publiek_name", "niet_pub_naam", 32),
        ],
        MAX_CONSOLE_ROWS,
    )
    print("")
    print_json_block(
        "Samenvatting:",
        {
            "liwo_rows": len(liwo_rows),
            "ldo_public_rows_scanned": public_ldo_rows_scanned,
            "ldo_nonpublic_rows_scanned": nonpublic_ldo_rows_scanned,
            "mapped": len(mapped_rows),
            "missing": len(missing_rows),
            "niet_publieke_ldo_matches": len(nonpublic_rows),
            "niet_publieke_ldo_statussen": dict(
                sorted(Counter(row["ldo_niet_publiek_status"] for row in nonpublic_rows).items())
            ),
            "match_method": "scenario.id",
            "match_pct_of_liwo": round((100.0 * len(mapped_rows) / len(liwo_rows)), 2)
            if liwo_rows
            else 0.0,
            "ldo_meta_kolommen": len(ldo_meta_columns),
            "external_meta_kolommen": len(external_meta_columns),
        },
    )
    print(f"Alle LIWO scenario-layers gevonden: {liwo_csv}")
    print(f"Alle LIWO scenario-layers gevonden Excel: {liwo_xlsx}")
    print(f"Hoofdoutput LIWO + LDO overzicht: {overview_csv}")
    print(f"Hoofdoutput LIWO + LDO overzicht Excel: {overview_xlsx}")
    print(f"Overzicht incl. external-processings meta: {overview_ext_csv}")
    print(f"Overzicht incl. external-processings meta Excel: {overview_ext_xlsx}")
    print(f"Mapping CSV: {map_csv}")
    print(f"Mapping Excel: {map_xlsx}")
    print(f"Ontbrekende IDs CSV: {missing_csv}")
    print(f"Ontbrekende IDs Excel: {missing_xlsx}")
    print(f"LIWO met niet-publiek LDO CSV: {nonpublic_csv}")
    print(f"LIWO met niet-publiek LDO Excel: {nonpublic_xlsx}")
    print(f"Samenvatting JSON: {summary_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
