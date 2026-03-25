#!/usr/bin/env python3
"""Vind mogelijke nieuwere LIWO scenario's in LDO via scenario-families.

Dit script is bedoeld als een eenvoudige en uitlegbare signalering.
Het bewijst dus niet definitief dat een LIWO-scenario vervangen is, maar het
laat wel op een veel strakkere manier zien waar dat waarschijnlijk zo is.

De kern van de methode is het idee van een "scenario-familie".
We zoeken niet meer naar alle willekeurige LDO-scenario's binnen 100 meter,
maar naar LDO-scenario's die waarschijnlijk tot dezelfde familie horen.

In dit script betekent "zelfde familie":
1. het LDO-kandidaatscenario ligt binnen 100 meter van de referentielocatie
2. `projectnaam` is exact gelijk
3. `gebiedsnaam` is exact gelijk
4. `naam doorbraaklocatie` is exact gelijk

Waarom zo:
- alleen op afstand zoeken geeft te veel ruis
- exacte coordinaten eisen is te streng; dezelfde breslocatie kan iets afwijken
- deze combinatie blijft simpel, maar sluit veel onwaarschijnlijke matches uit

Hoe de referentielocatie wordt bepaald:
- eerst gebruiken we de directe publieke LDO ID-match van het LIWO-scenario,
  als die geldige RD New coordinaten heeft
- als dat niet kan, gebruiken we het centroid van de LIWO WMS-bounding-box

Wanneer noemen we iets `mogelijk_nieuwer = ja`:
- er is een directe publieke oude LDO-match
- er is minstens een LDO-kandidaat uit dezelfde familie
- we nemen binnen die familie alleen de nieuwste kandidaat
- die nieuwste kandidaat heeft:
  - een `id` die minimaal 20 hoger is dan het oude LDO-scenario
  - een latere `created_at` dan het oude LDO-scenario

Belangrijke grenzen van deze methode:
- het script gebruikt geen scoremodel
- het script gebruikt geen fuzzy naamvergelijking
- het script kijkt alleen naar publieke LDO scenario's
- zonder directe publieke oude LDO-match kunnen we de familie niet hard bepalen,
  omdat LIWO zelf deze LDO-metadata niet bevat

Dat betekent dus:
- `mogelijk_nieuwer = ja` is een sterk signaal voor een nieuwere publieke
  versie binnen dezelfde scenario-familie
- maar een mens moet daarna nog steeds inhoudelijk controleren of het echt om
  dezelfde inhoudelijke vervanging gaat

Output in output/ldo/:
- liwo_mogelijk_nieuwere_scenarios_in_ldo.csv
- liwo_mogelijk_nieuwere_scenarios_in_ldo.xlsx
- liwo_mogelijk_nieuwere_scenarios_in_ldo_summary.json
"""

from __future__ import annotations

import math
import os
import re
from datetime import datetime
from xml.etree import ElementTree as ET

import requests

from _ldo_common import (
    get_base,
    get_liwo_base,
    get_token,
    iter_scenarios,
    load_env_fallback,
    make_session,
    meta_value,
    output_file,
    print_json_block,
    print_table,
    to_float,
    write_csv,
    write_excel,
    write_json,
)

# Instellingen
LIWO_TIMEOUT_SEC = 30
LDO_PAGINA_GROOTTE = 200
MAX_AANTAL_LDO_SCENARIOS = 0  # 0 = alles
DOEL_WORKSPACES = ["LIWO_Primair", "LIWO_Regionaal", "LIWO_RegionaalSysteem"]
BUFFER_AFSTAND_METER = 100.0
MINIMAAL_ID_VERSCHIL = 20
MAX_CONSOLE_ROWS = 20
WMS_NS = {"wms": "http://www.opengis.net/wms"}
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"
SMOKE_MAX_AANTAL_LDO_SCENARIOS = 50
SMOKE_MAX_AANTAL_LIWO_ROWS = 10
SMOKE_DOEL_WORKSPACES = ["LIWO_Primair"]
SMOKE_LIWO_ROWS = [
    {
        "workspace": "LIWO_Primair",
        "liwo_id": "310",
        "liwo_layer_name": "LIWO_Primair:scenario_310",
        "liwo_layer_title": "scenario_310",
        "liwo_layer_abstract": "",
        "_bbox_center_x_rdnew": None,
        "_bbox_center_y_rdnew": None,
    },
    {
        "workspace": "LIWO_Primair",
        "liwo_id": "317",
        "liwo_layer_name": "LIWO_Primair:scenario_317",
        "liwo_layer_title": "scenario_317",
        "liwo_layer_abstract": "",
        "_bbox_center_x_rdnew": None,
        "_bbox_center_y_rdnew": None,
    },
]
FAMILIE_MATCH_VELDEN = [
    ("ldo_projectnaam", "projectnaam"),
    ("ldo_gebiedsnaam", "gebiedsnaam"),
    ("ldo_naam_doorbraaklocatie", "naam_doorbraaklocatie"),
]

CONTROLE_FIELDNAMES = [
    "workspace",
    "liwo_id",
    "oud_ldo_id",
    "mogelijk_nieuw_ldo_id",
    "mogelijk_nieuw_id_verschil",
    "distance_m",
    "mogelijk_nieuw_ldo_created_at",
    "mogelijk_nieuw_is_nieuwste_in_familie",
    "mogelijk_nieuw_id_is_minimaal_20_hoger",
    "mogelijk_nieuw_heeft_latere_created_at",
    "mogelijk_nieuwer",
    "reden_beoordeling",
]

LIWO_FIELDNAMES = [
    "liwo_layer_name",
    "liwo_layer_title",
    "liwo_layer_abstract",
    # Beschikbare LIWO-velden uit WMS die nu bewust uit staan:
    # "liwo_layer_queryable",
    # "liwo_layer_opaque",
    # "liwo_layer_keyword_list",
    # "liwo_layer_crs_list",
    # "liwo_layer_style_names",
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
]

LDO_FIELDNAMES = [
    "mogelijk_nieuw_ldo_name",
    "mogelijk_nieuw_ldo_area_name",
    "mogelijk_nieuw_ldo_status",
    "mogelijk_nieuw_ldo_scenario_type",
    "mogelijk_nieuw_ldo_inundation_source",
    "mogelijk_nieuw_ldo_created_by_id",
    "mogelijk_nieuw_ldo_created_by_name",
    "mogelijk_nieuw_ldo_updated_at",
    "mogelijk_nieuw_ldo_updated_by_id",
    "mogelijk_nieuw_ldo_updated_by_name",
    "mogelijk_nieuw_projectnaam",
    "mogelijk_nieuw_gebiedsnaam",
    "mogelijk_nieuw_naam_doorbraaklocatie",
    "mogelijk_nieuw_scenariodatum",
    # Beschikbare LDO-velden die nu bewust uit staan:
    # "mogelijk_nieuw_ldo_tenant",
    # "mogelijk_nieuw_ldo_meta_version",
    # "mogelijk_nieuw_ldo_excel_import_id",
    # "mogelijk_nieuw_ldo_breach_growth_start",
    # "mogelijk_nieuw_ldo_x_rdnew",
    # "mogelijk_nieuw_ldo_y_rdnew",
    # "mogelijk_nieuw_ldo_breach_count",
    # "mogelijk_nieuw_ldo_raster_count",
    # "mogelijk_nieuw_ldo_file_count",
    # "mogelijk_nieuw_ldo_errors",
]

BASELINE_FIELDNAMES = [
    "oud_ldo_name",
    "oud_ldo_status",
    "oud_ldo_scenario_type",
    "oud_ldo_created_at",
    "oud_projectnaam",
    "oud_gebiedsnaam",
    "oud_naam_doorbraaklocatie",
    "oud_scenariodatum",
    # Beschikbare oude-LDO-velden die nu bewust uit staan:
    # "oud_ldo_area_name",
    # "oud_ldo_inundation_source",
    # "oud_ldo_created_by_id",
    # "oud_ldo_created_by_name",
    # "oud_ldo_updated_at",
    # "oud_ldo_updated_by_id",
    # "oud_ldo_updated_by_name",
    # "oud_ldo_x_rdnew",
    # "oud_ldo_y_rdnew",
]

BEOORDELING_FIELDNAMES = [
    "zelfde_projectnaam",
    "zelfde_gebiedsnaam",
    "zelfde_naam_doorbraaklocatie",
    "zelfde_familie",
    "heeft_directe_oude_ldo_match",
    "referentie_locatie_bron",
    "referentie_x_rdnew",
    "referentie_y_rdnew",
]

OUTPUT_FIELDNAMES = (
    CONTROLE_FIELDNAMES + LIWO_FIELDNAMES + LDO_FIELDNAMES + BASELINE_FIELDNAMES + BEOORDELING_FIELDNAMES
)


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


def parse_iso_datetime(value: str) -> datetime | None:
    """Parse an ISO datetime string.

    Parameters
    ----------
    value : str
        Value to inspect or format.

    Returns
    -------
    datetime | None
        Parsed datetime, or `None` when parsing fails.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


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
    return str(value).strip()


def same_nonempty_text(left: str, right: str) -> bool:
    """Return whether two non-empty text values match.

    Parameters
    ----------
    left : str
        Left value to compare.
    right : str
        Right value to compare.

    Returns
    -------
    bool
        True when the check succeeds.
    """
    return bool(left and right and left == right)


def bbox_center_epsg28992(layer) -> tuple[float | None, float | None]:
    """Return the center point of a bbox in EPSG:28992.

    Parameters
    ----------
    layer : Any
        Layer record to inspect.

    Returns
    -------
    tuple[float | None, float | None]
        Tuple with the requested values.
    """
    for node in layer.findall("wms:BoundingBox", WMS_NS):
        crs = (node.attrib.get("CRS") or node.attrib.get("SRS") or "").strip()
        if crs != "EPSG:28992":
            continue

        minx = to_float(node.attrib.get("minx"))
        miny = to_float(node.attrib.get("miny"))
        maxx = to_float(node.attrib.get("maxx"))
        maxy = to_float(node.attrib.get("maxy"))
        if None in (minx, miny, maxx, maxy):
            return None, None
        return ((minx + maxx) / 2.0, (miny + maxy) / 2.0)

    return None, None


def haal_liwo_scenario_lagen_op(
    liwo_base_url: str,
    doel_workspaces: list[str],
) -> list[dict[str, object]]:
    """Fetch LIWO scenario layers for the selected workspaces.

    Parameters
    ----------
    liwo_base_url : str
        Base URL for the LIWO API.
    doel_workspaces : list[str]
        Workspaces that should be scanned.

    Returns
    -------
    list[dict[str, object]]
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

    rows: list[dict[str, object]] = []
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

        center_x, center_y = bbox_center_epsg28992(layer)
        rows.append(
            {
                "workspace": workspace,
                "liwo_id": liwo_id,
                "liwo_layer_name": layer_name,
                "liwo_layer_title": get_wms_text(layer, "wms:Title"),
                "liwo_layer_abstract": get_wms_text(layer, "wms:Abstract"),
                # Beschikbare LIWO-velden die nu bewust uit staan:
                # "liwo_layer_queryable": cell_text(layer.attrib.get("queryable")),
                # "liwo_layer_opaque": cell_text(layer.attrib.get("opaque")),
                # "liwo_layer_keyword_list": "",
                # "liwo_layer_crs_list": "",
                # "liwo_layer_style_names": "",
                "_bbox_center_x_rdnew": center_x,
                "_bbox_center_y_rdnew": center_y,
                # "liwo_layer_bbox_epsg28992_minx": "",
                # "liwo_layer_bbox_epsg28992_miny": "",
                # "liwo_layer_bbox_epsg28992_maxx": "",
                # "liwo_layer_bbox_epsg28992_maxy": "",
            }
        )

    rows.sort(key=lambda row: (str(row["workspace"]), int(str(row["liwo_id"]))))
    return rows


def maak_ldo_row(scenario: dict) -> dict[str, object]:
    """Build one normalized LDO row.

    Parameters
    ----------
    scenario : dict
        Scenario payload to inspect.

    Returns
    -------
    dict[str, object]
        Result dictionary.
    """
    meta = scenario.get("meta", {}) if isinstance(scenario, dict) else {}
    if not isinstance(meta, dict):
        meta = {}
    created_by = scenario.get("created_by", {}) if isinstance(scenario, dict) else {}
    if not isinstance(created_by, dict):
        created_by = {}
    updated_by = scenario.get("updated_by", {}) if isinstance(scenario, dict) else {}
    if not isinstance(updated_by, dict):
        updated_by = {}

    x_rdnew = to_float(
        meta_value(
            meta,
            "x-coordinaten doorbraaklocatie/effectgebied",
            "x-coordinaten doorbraaklocatie",
        )
    )
    y_rdnew = to_float(
        meta_value(
            meta,
            "y-coordinaten doorbraaklocatie/effectgebied",
            "y-coordinaten doorbraaklocatie",
        )
    )

    created_at = cell_text(scenario.get("created_at"))
    return {
        "ldo_id": cell_text(scenario.get("id")),
        "ldo_name": cell_text(scenario.get("name")),
        "ldo_area_name": cell_text(scenario.get("area_name")),
        "ldo_inundation_source": cell_text(scenario.get("inundation_source")),
        # Beschikbare LDO-velden die nu bewust uit staan:
        # "ldo_tenant": cell_text(scenario.get("tenant")),
        # "ldo_meta_version": cell_text(scenario.get("meta_version")),
        # "ldo_excel_import_id": cell_text(scenario.get("excel_import_id")),
        # "ldo_breach_growth_start": cell_text(scenario.get("breach_growth_start")),
        "ldo_created_at": created_at,
        "_ldo_created_at_dt": parse_iso_datetime(created_at),
        "ldo_status": cell_text(scenario.get("status")),
        "ldo_scenario_type": cell_text(scenario.get("scenario_type")),
        "ldo_created_by_id": cell_text(created_by.get("id")),
        "ldo_created_by_name": cell_text(created_by.get("name")),
        "ldo_updated_at": cell_text(scenario.get("updated_at")),
        "ldo_updated_by_id": cell_text(updated_by.get("id")),
        "ldo_updated_by_name": cell_text(updated_by.get("name")),
        "ldo_projectnaam": cell_text(meta_value(meta, "projectnaam")),
        "ldo_gebiedsnaam": cell_text(meta_value(meta, "gebiedsnaam")),
        "ldo_naam_doorbraaklocatie": cell_text(meta_value(meta, "naam doorbraaklocatie")),
        "ldo_scenariodatum": cell_text(meta_value(meta, "scenariodatum")),
        "ldo_x_rdnew": x_rdnew,
        "ldo_y_rdnew": y_rdnew,
        # "ldo_errors": cell_text(scenario.get("errors")),
    }


def haal_publieke_ldo_scenarios_op(
    session: requests.Session,
    ldo_base_url: str,
    max_aantal_ldo_scenarios: int,
) -> tuple[dict[str, dict[str, object]], list[dict[str, object]], int]:
    """Fetch public LDO scenarios.

    Parameters
    ----------
    session : requests.Session
        Authenticated requests session.
    ldo_base_url : str
        Base URL for the LDO API.
    max_aantal_ldo_scenarios : int
        Maximum number of LDO scenarios to scan. Use `0` for all.

    Returns
    -------
    tuple[dict[str, dict[str, object]], list[dict[str, object]], int]
        Tuple with the requested values.
    """
    by_ldo_id: dict[str, dict[str, object]] = {}
    rows_with_coords: list[dict[str, object]] = []
    total_rows = 0

    for scenario in iter_scenarios(
        session=session,
        base=ldo_base_url,
        limit=LDO_PAGINA_GROOTTE,
        max_scenarios=max_aantal_ldo_scenarios,
        mode_public=True,
    ):
        ldo_id = str(scenario.get("id", "")).strip()
        if not ldo_id:
            continue

        total_rows += 1
        row = maak_ldo_row(scenario)
        by_ldo_id[ldo_id] = row
        if row["ldo_x_rdnew"] is not None and row["ldo_y_rdnew"] is not None:
            rows_with_coords.append(row)

    return by_ldo_id, rows_with_coords, total_rows


def grid_key(x_value: float, y_value: float) -> tuple[int, int]:
    """Build a grid key from a coordinate pair.

    Parameters
    ----------
    x_value : float
        X-coordinate value.
    y_value : float
        Y-coordinate value.

    Returns
    -------
    tuple[int, int]
        Tuple with the requested values.
    """
    return (
        int(math.floor(x_value / BUFFER_AFSTAND_METER)),
        int(math.floor(y_value / BUFFER_AFSTAND_METER)),
    )


def bouw_ldo_spatial_index(
    ldo_rows_with_coords: list[dict[str, object]],
) -> dict[tuple[int, int], list[dict[str, object]]]:
    """Build a lightweight spatial index for LDO rows.

    Parameters
    ----------
    ldo_rows_with_coords : list[dict[str, object]]
        LDO rows that include usable coordinates.

    Returns
    -------
    dict[tuple[int, int], list[dict[str, object]]]
        Result dictionary.
    """
    index: dict[tuple[int, int], list[dict[str, object]]] = {}
    for row in ldo_rows_with_coords:
        x_value = row["ldo_x_rdnew"]
        y_value = row["ldo_y_rdnew"]
        if x_value is None or y_value is None:
            continue
        index.setdefault(grid_key(float(x_value), float(y_value)), []).append(row)
    return index


def bepaal_referentiepunt(
    liwo_row: dict[str, object],
    baseline_row: dict[str, object] | None,
) -> tuple[str, float | None, float | None]:
    """Determine the reference point for a LIWO scenario.

    Parameters
    ----------
    liwo_row : dict[str, object]
        LIWO row used for the comparison.
    baseline_row : dict[str, object] | None
        Baseline row used for the comparison.

    Returns
    -------
    tuple[str, float | None, float | None]
        Tuple with the requested values.
    """
    if baseline_row is not None:
        x_value = baseline_row.get("ldo_x_rdnew")
        y_value = baseline_row.get("ldo_y_rdnew")
        if x_value is not None and y_value is not None:
            return "directe_ldo_match_rdnew", float(x_value), float(y_value)

    x_value = liwo_row.get("_bbox_center_x_rdnew")
    y_value = liwo_row.get("_bbox_center_y_rdnew")
    if x_value is not None and y_value is not None:
        return "liwo_bbox_centroid_epsg28992", float(x_value), float(y_value)

    return "", None, None


def vind_kandidaten_binnen_buffer(
    referentie_x: float,
    referentie_y: float,
    ldo_index: dict[tuple[int, int], list[dict[str, object]]],
) -> list[tuple[dict[str, object], float]]:
    """Find candidate LDO scenarios inside the search buffer.

    Parameters
    ----------
    referentie_x : float
        Reference x-coordinate in RD New.
    referentie_y : float
        Reference y-coordinate in RD New.
    ldo_index : dict[tuple[int, int], list[dict[str, object]]]
        Spatial index built from LDO rows.

    Returns
    -------
    list[tuple[dict[str, object], float]]
        Collected items.
    """
    center_cell_x, center_cell_y = grid_key(referentie_x, referentie_y)
    nearby: list[tuple[dict[str, object], float]] = []
    max_sq = BUFFER_AFSTAND_METER * BUFFER_AFSTAND_METER

    for delta_x in (-1, 0, 1):
        for delta_y in (-1, 0, 1):
            cell = (center_cell_x + delta_x, center_cell_y + delta_y)
            for candidate in ldo_index.get(cell, []):
                cand_x = float(candidate["ldo_x_rdnew"])
                cand_y = float(candidate["ldo_y_rdnew"])
                diff_x = cand_x - referentie_x
                if abs(diff_x) > BUFFER_AFSTAND_METER:
                    continue
                diff_y = cand_y - referentie_y
                if abs(diff_y) > BUFFER_AFSTAND_METER:
                    continue

                sq_distance = diff_x * diff_x + diff_y * diff_y
                if sq_distance > max_sq:
                    continue

                nearby.append((candidate, math.sqrt(sq_distance)))

    nearby.sort(key=lambda item: (item[1], int(str(item[0]["ldo_id"]))))
    return nearby


def familie_match_flags(
    baseline_row: dict[str, object] | None,
    candidate_row: dict[str, object],
) -> dict[str, str]:
    """Derive family-match flags for a baseline and candidate.

    Parameters
    ----------
    baseline_row : dict[str, object] | None
        Baseline row used for the comparison.
    candidate_row : dict[str, object]
        Candidate row used for the comparison.

    Returns
    -------
    dict[str, str]
        Result dictionary.
    """
    if baseline_row is None:
        return {
            "zelfde_projectnaam": "",
            "zelfde_gebiedsnaam": "",
            "zelfde_naam_doorbraaklocatie": "",
            "zelfde_familie": "",
        }

    same_project = same_nonempty_text(
        str(baseline_row["ldo_projectnaam"]),
        str(candidate_row["ldo_projectnaam"]),
    )
    same_gebied = same_nonempty_text(
        str(baseline_row["ldo_gebiedsnaam"]),
        str(candidate_row["ldo_gebiedsnaam"]),
    )
    same_doorbraak = same_nonempty_text(
        str(baseline_row["ldo_naam_doorbraaklocatie"]),
        str(candidate_row["ldo_naam_doorbraaklocatie"]),
    )
    zelfde_familie = same_project and same_gebied and same_doorbraak
    return {
        "zelfde_projectnaam": "ja" if same_project else "nee",
        "zelfde_gebiedsnaam": "ja" if same_gebied else "nee",
        "zelfde_naam_doorbraaklocatie": "ja" if same_doorbraak else "nee",
        "zelfde_familie": "ja" if zelfde_familie else "nee",
    }


def is_candidate_nieuwer(
    baseline_row: dict[str, object] | None,
    candidate_row: dict[str, object],
) -> tuple[bool, int, str, str]:
    """Return whether the candidate looks newer than the baseline.

    Parameters
    ----------
    baseline_row : dict[str, object] | None
        Baseline row used for the comparison.
    candidate_row : dict[str, object]
        Candidate row used for the comparison.

    Returns
    -------
    tuple[bool, int, str, str]
        Tuple with the requested values.
    """
    if baseline_row is None:
        return False, 0, "nee", "nee"

    id_verschil = int(str(candidate_row["ldo_id"])) - int(str(baseline_row["ldo_id"]))
    has_minimaal_20_hoger_id = id_verschil >= MINIMAAL_ID_VERSCHIL
    baseline_created_at_dt = baseline_row.get("_ldo_created_at_dt")
    candidate_created_at_dt = candidate_row.get("_ldo_created_at_dt")
    has_later_created_at = (
        baseline_created_at_dt is not None
        and candidate_created_at_dt is not None
        and candidate_created_at_dt > baseline_created_at_dt
    )
    return (
        has_minimaal_20_hoger_id and has_later_created_at,
        id_verschil,
        "ja" if has_minimaal_20_hoger_id else "nee",
        "ja" if has_later_created_at else "nee",
    )


def kies_nieuwste_candidate(
    family_candidates: list[tuple[dict[str, object], float]],
) -> dict[str, object] | None:
    """Choose the newest candidate within one family.

    Parameters
    ----------
    family_candidates : list[tuple[dict[str, object], float]]
        Candidate rows that belong to the same family.

    Returns
    -------
    dict[str, object] | None
        Result dictionary.
    """
    if not family_candidates:
        return None
    return max(
        (candidate_row for candidate_row, _ in family_candidates),
        key=lambda row: (
            row.get("_ldo_created_at_dt") or datetime.min,
            int(str(row["ldo_id"])),
        ),
    )


def maak_row(
    liwo_row: dict[str, object],
    baseline_row: dict[str, object] | None,
    candidate_row: dict[str, object],
    referentie_locatie_bron: str,
    referentie_x: float,
    referentie_y: float,
    distance_m: float,
    candidate_is_nieuwste_in_familie: bool,
    mogelijk_nieuwer: str,
    reden_beoordeling: str,
) -> dict[str, object]:
    """Build one output row.

    Parameters
    ----------
    liwo_row : dict[str, object]
        LIWO row used for the comparison.
    baseline_row : dict[str, object] | None
        Baseline row used for the comparison.
    candidate_row : dict[str, object]
        Candidate row used for the comparison.
    referentie_locatie_bron : str
        Label that explains which reference location was used.
    referentie_x : float
        Reference x-coordinate in RD New.
    referentie_y : float
        Reference y-coordinate in RD New.
    distance_m : float
        Distance in meters between reference points.
    candidate_is_nieuwste_in_familie : bool
        Whether this candidate is the newest within its family.
    mogelijk_nieuwer : str
        Whether the candidate appears to be newer.
    reden_beoordeling : str
        Reason for the final assessment.

    Returns
    -------
    dict[str, object]
        Result dictionary.
    """
    family_flags = familie_match_flags(baseline_row, candidate_row)
    (
        _,
        mogelijk_nieuw_id_verschil,
        mogelijk_nieuw_id_is_minimaal_20_hoger,
        mogelijk_nieuw_heeft_latere_created_at,
    ) = is_candidate_nieuwer(
        baseline_row,
        candidate_row,
    )

    return {
        "workspace": liwo_row["workspace"],
        "liwo_id": liwo_row["liwo_id"],
        "oud_ldo_id": "" if baseline_row is None else baseline_row["ldo_id"],
        "mogelijk_nieuw_ldo_id": candidate_row["ldo_id"],
        "mogelijk_nieuw_id_verschil": mogelijk_nieuw_id_verschil,
        "distance_m": round(distance_m, 3),
        "mogelijk_nieuw_ldo_created_at": candidate_row["ldo_created_at"],
        "mogelijk_nieuw_is_nieuwste_in_familie": "ja"
        if candidate_is_nieuwste_in_familie
        else "nee",
        "mogelijk_nieuw_id_is_minimaal_20_hoger": mogelijk_nieuw_id_is_minimaal_20_hoger,
        "mogelijk_nieuw_heeft_latere_created_at": mogelijk_nieuw_heeft_latere_created_at,
        "mogelijk_nieuwer": mogelijk_nieuwer,
        "reden_beoordeling": reden_beoordeling,
        "liwo_layer_name": liwo_row["liwo_layer_name"],
        "liwo_layer_title": liwo_row["liwo_layer_title"],
        "liwo_layer_abstract": cell_text(liwo_row.get("liwo_layer_abstract")),
        "mogelijk_nieuw_ldo_name": candidate_row["ldo_name"],
        "mogelijk_nieuw_ldo_area_name": candidate_row["ldo_area_name"],
        "mogelijk_nieuw_ldo_status": candidate_row["ldo_status"],
        "mogelijk_nieuw_ldo_scenario_type": candidate_row["ldo_scenario_type"],
        "mogelijk_nieuw_ldo_inundation_source": candidate_row["ldo_inundation_source"],
        "mogelijk_nieuw_ldo_created_by_id": candidate_row["ldo_created_by_id"],
        "mogelijk_nieuw_ldo_created_by_name": candidate_row["ldo_created_by_name"],
        "mogelijk_nieuw_ldo_updated_at": candidate_row["ldo_updated_at"],
        "mogelijk_nieuw_ldo_updated_by_id": candidate_row["ldo_updated_by_id"],
        "mogelijk_nieuw_ldo_updated_by_name": candidate_row["ldo_updated_by_name"],
        "mogelijk_nieuw_projectnaam": candidate_row["ldo_projectnaam"],
        "mogelijk_nieuw_gebiedsnaam": candidate_row["ldo_gebiedsnaam"],
        "mogelijk_nieuw_naam_doorbraaklocatie": candidate_row["ldo_naam_doorbraaklocatie"],
        "mogelijk_nieuw_scenariodatum": candidate_row["ldo_scenariodatum"],
        "oud_ldo_name": "" if baseline_row is None else baseline_row["ldo_name"],
        "oud_ldo_status": "" if baseline_row is None else baseline_row["ldo_status"],
        "oud_ldo_scenario_type": ""
        if baseline_row is None
        else baseline_row["ldo_scenario_type"],
        "oud_ldo_created_at": ""
        if baseline_row is None
        else baseline_row["ldo_created_at"],
        "oud_projectnaam": ""
        if baseline_row is None
        else baseline_row["ldo_projectnaam"],
        "oud_gebiedsnaam": ""
        if baseline_row is None
        else baseline_row["ldo_gebiedsnaam"],
        "oud_naam_doorbraaklocatie": ""
        if baseline_row is None
        else baseline_row["ldo_naam_doorbraaklocatie"],
        "oud_scenariodatum": ""
        if baseline_row is None
        else baseline_row["ldo_scenariodatum"],
        # Beschikbare oude-LDO-velden die nu bewust uit staan:
        # "oud_ldo_area_name": ""
        # if baseline_row is None
        # else baseline_row["ldo_area_name"],
        # "oud_ldo_inundation_source": ""
        # if baseline_row is None
        # else baseline_row["ldo_inundation_source"],
        **family_flags,
        "heeft_directe_oude_ldo_match": "ja" if baseline_row is not None else "nee",
        "referentie_locatie_bron": referentie_locatie_bron,
        "referentie_x_rdnew": round(referentie_x, 3),
        "referentie_y_rdnew": round(referentie_y, 3),
    }


def maak_output_rows(
    liwo_rows: list[dict[str, object]],
    public_by_id: dict[str, dict[str, object]],
    ldo_index: dict[tuple[int, int], list[dict[str, object]]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, int]]:
    """Build all output rows for the report.

    Parameters
    ----------
    liwo_rows : list[dict[str, object]]
        LIWO rows used as input for the comparison.
    public_by_id : dict[str, dict[str, object]]
        Lookup with public LDO rows keyed by id.
    ldo_index : dict[tuple[int, int], list[dict[str, object]]]
        Spatial index built from LDO rows.

    Returns
    -------
    tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, int]]
        Tuple with the requested values.
    """
    family_candidate_rows: list[dict[str, object]] = []
    possible_newer_rows: list[dict[str, object]] = []
    no_baseline_rows: list[dict[str, object]] = []

    count_direct_baseline = 0
    count_no_direct_baseline = 0
    count_using_bbox_centroid = 0
    count_no_reference_location = 0
    liwo_with_family_candidates: set[str] = set()
    liwo_with_possible_newer: set[str] = set()
    liwo_without_baseline_with_candidates: set[str] = set()

    for liwo_row in liwo_rows:
        liwo_id = str(liwo_row["liwo_id"])
        baseline_row = public_by_id.get(liwo_id)
        if baseline_row is not None:
            count_direct_baseline += 1
        else:
            count_no_direct_baseline += 1

        referentie_locatie_bron, referentie_x, referentie_y = bepaal_referentiepunt(
            liwo_row=liwo_row,
            baseline_row=baseline_row,
        )
        if referentie_locatie_bron == "liwo_bbox_centroid_epsg28992":
            count_using_bbox_centroid += 1

        if referentie_x is None or referentie_y is None:
            count_no_reference_location += 1
            continue

        nearby_candidates = vind_kandidaten_binnen_buffer(
            referentie_x=referentie_x,
            referentie_y=referentie_y,
            ldo_index=ldo_index,
        )

        if baseline_row is None:
            if not nearby_candidates:
                continue
            liwo_without_baseline_with_candidates.add(liwo_id)
            for candidate_row, distance_m in nearby_candidates:
                no_baseline_rows.append(
                    maak_row(
                        liwo_row=liwo_row,
                        baseline_row=None,
                        candidate_row=candidate_row,
                        referentie_locatie_bron=referentie_locatie_bron,
                        referentie_x=referentie_x,
                        referentie_y=referentie_y,
                        distance_m=distance_m,
                        candidate_is_nieuwste_in_familie=False,
                        mogelijk_nieuwer="nee",
                        reden_beoordeling=(
                            "geen directe publieke oude LDO-match; nabij scenario "
                            "wordt wel gezien, maar familie is niet hard te bepalen"
                        ),
                    )
                )
            continue

        family_candidates: list[tuple[dict[str, object], float]] = []
        for candidate_row, distance_m in nearby_candidates:
            if candidate_row["ldo_id"] == baseline_row["ldo_id"]:
                continue
            if familie_match_flags(baseline_row, candidate_row)["zelfde_familie"] != "ja":
                continue
            family_candidates.append((candidate_row, distance_m))

        if not family_candidates:
            continue

        liwo_with_family_candidates.add(liwo_id)
        newest_candidate = kies_nieuwste_candidate(family_candidates)

        for candidate_row, distance_m in family_candidates:
            is_newest = newest_candidate is not None and candidate_row["ldo_id"] == newest_candidate["ldo_id"]
            is_nieuwer, _, _, _ = is_candidate_nieuwer(baseline_row, candidate_row)
            row = maak_row(
                liwo_row=liwo_row,
                baseline_row=baseline_row,
                candidate_row=candidate_row,
                referentie_locatie_bron=referentie_locatie_bron,
                referentie_x=referentie_x,
                referentie_y=referentie_y,
                distance_m=distance_m,
                candidate_is_nieuwste_in_familie=is_newest,
                mogelijk_nieuwer="ja" if is_newest and is_nieuwer else "nee",
                reden_beoordeling=(
                    "zelfde familie binnen 100 meter, maar niet het nieuwste scenario "
                    "binnen die familie"
                    if not is_newest
                    else (
                        "nieuwste scenario binnen dezelfde familie, met id minimaal 20 "
                        "hoger en latere created_at dan het oude LDO-scenario"
                        if is_nieuwer
                        else "nieuwste scenario binnen dezelfde familie, maar niet zowel "
                        "minimaal 20 hoger in id als later in created_at dan het oude "
                        "LDO-scenario"
                    )
                ),
            )
            family_candidate_rows.append(row)

            if row["mogelijk_nieuwer"] == "ja":
                possible_newer_rows.append(row)
                liwo_with_possible_newer.add(liwo_id)

    counts = {
        "liwo_with_directe_oude_ldo_match": count_direct_baseline,
        "liwo_without_directe_oude_ldo_match": count_no_direct_baseline,
        "liwo_using_bbox_centroid_as_reference": count_using_bbox_centroid,
        "liwo_without_reference_location": count_no_reference_location,
        "unique_liwo_with_family_candidates": len(liwo_with_family_candidates),
        "unique_liwo_with_possible_newer": len(liwo_with_possible_newer),
        "unique_liwo_without_directe_oude_ldo_match_with_nearby_candidates": len(
            liwo_without_baseline_with_candidates
        ),
    }

    return family_candidate_rows, possible_newer_rows, no_baseline_rows, counts


def schrijf_outputbestanden(
    family_candidate_rows: list[dict[str, object]],
    possible_newer_rows: list[dict[str, object]],
    no_baseline_rows: list[dict[str, object]],
    liwo_rows: list[dict[str, object]],
    public_ldo_rows_scanned: int,
    public_ldo_rows_with_coordinates: int,
    counts: dict[str, int],
) -> tuple[object, ...]:
    """Write the output files for this script.

    Parameters
    ----------
    family_candidate_rows : list[dict[str, object]]
        Rows that describe family candidates.
    possible_newer_rows : list[dict[str, object]]
        Rows that describe possible newer scenarios.
    no_baseline_rows : list[dict[str, object]]
        Rows without a usable baseline scenario.
    liwo_rows : list[dict[str, object]]
        LIWO rows used as input for the comparison.
    public_ldo_rows_scanned : int
        Number of public LDO rows that were scanned.
    public_ldo_rows_with_coordinates : int
        Number of public LDO rows with usable coordinates.
    counts : dict[str, int]
        Summary counts collected during processing.

    Returns
    -------
    tuple[object, ...]
        Tuple with the requested values.
    """
    possible_newer_csv = output_file("liwo_mogelijk_nieuwere_scenarios_in_ldo.csv")
    possible_newer_xlsx = output_file("liwo_mogelijk_nieuwere_scenarios_in_ldo.xlsx")
    summary_json = output_file("liwo_mogelijk_nieuwere_scenarios_in_ldo_summary.json")

    write_csv(possible_newer_csv, possible_newer_rows, OUTPUT_FIELDNAMES)
    write_excel(
        possible_newer_xlsx,
        possible_newer_rows,
        OUTPUT_FIELDNAMES,
        "Mogelijk nieuwer",
    )

    write_json(
        summary_json,
        {
            "liwo_rows": len(liwo_rows),
            "public_ldo_rows_scanned": public_ldo_rows_scanned,
            "public_ldo_rows_with_coordinates": public_ldo_rows_with_coordinates,
            "buffer_distance_m": BUFFER_AFSTAND_METER,
            "minimaal_id_verschil": MINIMAAL_ID_VERSCHIL,
            "familie_match_velden": [label for _, label in FAMILIE_MATCH_VELDEN],
            "family_candidate_rows": len(family_candidate_rows),
            "possible_newer_rows": len(possible_newer_rows),
            "zonder_directe_oude_ldo_match_en_wel_nabij_rows": len(no_baseline_rows),
            **counts,
            "outputs": {
                "liwo_mogelijk_nieuwere_scenarios_in_ldo_csv": str(possible_newer_csv),
                "liwo_mogelijk_nieuwere_scenarios_in_ldo_xlsx": str(possible_newer_xlsx),
            },
        },
    )

    return (
        possible_newer_csv,
        possible_newer_xlsx,
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
            f"max_liwo_rows={SMOKE_MAX_AANTAL_LIWO_ROWS}"
        )

    print("Stap 1/3: LIWO scenario-layers ophalen...")
    if SMOKE_MODE:
        liwo_rows = SMOKE_LIWO_ROWS[:SMOKE_MAX_AANTAL_LIWO_ROWS]
    else:
        liwo_rows = haal_liwo_scenario_lagen_op(liwo_base_url, doel_workspaces)
    print(f"Gevonden LIWO scenario-layers: {len(liwo_rows)}")

    print("Stap 2/3: publieke LDO scenario's ophalen...")
    public_by_id, public_with_coords, public_ldo_rows_scanned = haal_publieke_ldo_scenarios_op(
        session=session,
        ldo_base_url=ldo_base_url,
        max_aantal_ldo_scenarios=max_aantal_ldo_scenarios,
    )
    print(f"Publieke LDO scenario's gescand: {public_ldo_rows_scanned}")
    print(f"Publieke LDO scenario's met coordinaten: {len(public_with_coords)}")

    print("Stap 3/3: kandidaten uit dezelfde familie zoeken...")
    ldo_index = bouw_ldo_spatial_index(public_with_coords)
    (
        family_candidate_rows,
        possible_newer_rows,
        no_baseline_rows,
        counts,
    ) = maak_output_rows(
        liwo_rows=liwo_rows,
        public_by_id=public_by_id,
        ldo_index=ldo_index,
    )
    print(f"Kandidaten uit dezelfde familie: {len(family_candidate_rows)}")
    print(f"Mogelijk nieuwere kandidaten: {len(possible_newer_rows)}")
    print(
        "Zonder directe oude LDO-match maar wel nabij scenario: "
        f"{len(no_baseline_rows)}"
    )

    (
        possible_newer_csv,
        possible_newer_xlsx,
        summary_json,
    ) = schrijf_outputbestanden(
        family_candidate_rows=family_candidate_rows,
        possible_newer_rows=possible_newer_rows,
        no_baseline_rows=no_baseline_rows,
        liwo_rows=liwo_rows,
        public_ldo_rows_scanned=public_ldo_rows_scanned,
        public_ldo_rows_with_coordinates=len(public_with_coords),
        counts=counts,
    )

    print("")
    print("Voorbeeld mogelijke nieuwere kandidaten:")
    print_table(
        possible_newer_rows,
        [
            ("workspace", "workspace", 20),
            ("liwo_id", "liwo_id", 10),
            ("oud_ldo_id", "oud_ldo_id", 12),
            ("mogelijk_nieuw_ldo_id", "mogelijk_nieuw_ldo_id", 20),
            ("distance_m", "distance_m", 10),
            ("mogelijk_nieuw_ldo_created_at", "nieuw_created_at", 22),
        ],
        MAX_CONSOLE_ROWS,
    )
    print("")
    print_json_block(
        "Samenvatting:",
        {
            "liwo_rows": len(liwo_rows),
            "public_ldo_rows_scanned": public_ldo_rows_scanned,
            "public_ldo_rows_with_coordinates": len(public_with_coords),
            "buffer_distance_m": BUFFER_AFSTAND_METER,
            "minimaal_id_verschil": MINIMAAL_ID_VERSCHIL,
            "familie_match_velden": [label for _, label in FAMILIE_MATCH_VELDEN],
            "family_candidate_rows": len(family_candidate_rows),
            "possible_newer_rows": len(possible_newer_rows),
            "zonder_directe_oude_ldo_match_en_wel_nabij_rows": len(no_baseline_rows),
            **counts,
        },
    )
    print(f"Mogelijk nieuwere CSV: {possible_newer_csv}")
    print(f"Mogelijk nieuwere Excel: {possible_newer_xlsx}")
    print(f"Samenvatting JSON: {summary_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
