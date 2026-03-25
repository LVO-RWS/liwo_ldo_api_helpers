#!/usr/bin/env python3
"""Download LIWO WFS- en WCS-lagen in bulk zonder afhankelijk te zijn van andere scripts."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import requests

from _liwo_common import get_base, get_xml, load_env_fallback, local_name, print_json_block

try:
    from tqdm import tqdm
except Exception:
    tqdm = None

# Instellingen
DOWNLOAD_TYPES = [
    "wfs",
    "wcs",
]
WORKSPACES = []  # [] = alle workspaces
ALLEEN_SCENARIO_LAGEN = False
MAX_ITEMS_PER_SERVICE = 0  # 0 = alles
OVERSCHRIJF_BESTAANDE_BESTANDEN = False
TIMEOUT_SEC = 180
WCS_VERSIE = "2.0.1"
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"


def log(message: str) -> None:
    """Print a log message with a timestamp.

    Parameters
    ----------
    message : str
        Message to log.
    """
    if tqdm is not None:
        tqdm.write(message)
    else:
        print(message)


def iter_with_progress(items: list[str], description: str, unit: str):
    """Yield items with optional progress reporting.

    Parameters
    ----------
    items : list[str]
        Items to iterate over or inspect.
    description : str
        Progress label shown while iterating.
    unit : str
        Unit label shown while iterating.

    Returns
    -------
    Any
        Original items or a tqdm-wrapped iterator.
    """
    if tqdm is None:
        return items
    return tqdm(items, desc=description, unit=unit, leave=True)


def sanitize_name(value: str) -> str:
    """Sanitize a name for safe filesystem use.

    Parameters
    ----------
    value : str
        Value to inspect or format.

    Returns
    -------
    str
        Text result.
    """
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("_") or "item"


def discover_workspaces(base_url: str) -> list[str]:
    """Discover workspaces.

    Parameters
    ----------
    base_url : str
        Base URL for the request.

    Returns
    -------
    list[str]
        Collected items.
    """
    root = get_xml(
        f"{base_url}/wms",
        {"service": "WMS", "request": "GetCapabilities", "version": "1.3.0"},
        timeout=TIMEOUT_SEC,
    )
    workspaces: set[str] = set()
    for element in root.iter():
        if local_name(element.tag) != "Name":
            continue
        text = (element.text or "").strip()
        if ":" not in text:
            continue
        workspaces.add(text.split(":", 1)[0].strip())
    return sorted(workspaces)


def list_wfs_layers(base_url: str, workspace: str, alleen_scenario_lagen: bool) -> list[str]:
    """List WFS layers.

    Parameters
    ----------
    base_url : str
        Base URL for the request.
    workspace : str
        Workspace name to inspect.
    alleen_scenario_lagen : bool
        Whether to keep only layers that look like scenario layers.

    Returns
    -------
    list[str]
        Collected items.
    """
    root = get_xml(
        f"{base_url}/{workspace}/wfs",
        {"service": "WFS", "request": "GetCapabilities", "version": "2.0.0"},
        timeout=TIMEOUT_SEC,
    )
    rows: list[str] = []
    seen: set[str] = set()
    for element in root.iter():
        if local_name(element.tag) != "Name":
            continue
        name = (element.text or "").strip()
        if not name.startswith(f"{workspace}:"):
            continue
        if alleen_scenario_lagen and ":scenario_" not in name:
            continue
        if name in seen:
            continue
        seen.add(name)
        rows.append(name)
    return rows


def list_wcs_coverages(
    wcs_base_url: str,
    version: str,
    workspaces_filter: list[str],
    alleen_scenario_lagen: bool,
) -> list[str]:
    """List WCS coverages.

    Parameters
    ----------
    wcs_base_url : str
        Base URL for the WCS service.
    version : str
        Dataset version to download.
    workspaces_filter : list[str]
        Optional workspaces to include.
    alleen_scenario_lagen : bool
        Whether to keep only layers that look like scenario layers.

    Returns
    -------
    list[str]
        Collected items.
    """
    response = requests.get(
        f"{wcs_base_url}/wcs",
        params={"service": "WCS", "request": "GetCapabilities", "version": version},
        timeout=TIMEOUT_SEC,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)

    if version == "2.0.1":
        namespaces = {"wcs": "http://www.opengis.net/wcs/2.0"}
        values = [
            (element.text or "").strip()
            for element in root.findall(".//wcs:CoverageSummary/wcs:CoverageId", namespaces)
        ]
    else:
        namespaces = {"wcs": "http://www.opengis.net/wcs"}
        values = [
            (element.text or "").strip()
            for element in root.findall(".//wcs:CoverageOfferingBrief/wcs:name", namespaces)
        ]

    rows = [value for value in values if value]
    if workspaces_filter:
        rows = [value for value in rows if value.split("__", 1)[0] in workspaces_filter]
    if alleen_scenario_lagen:
        rows = [value for value in rows if "scenario_" in value]
    return sorted(dict.fromkeys(rows))


def take_items(rows: list[str], max_items_per_service: int) -> list[str]:
    """Take items.

    Parameters
    ----------
    rows : list[str]
        Rows to write or print.
    max_items_per_service : int
        Maximum number of layers or coverages to process per service.

    Returns
    -------
    list[str]
        Collected items.
    """
    if max_items_per_service > 0:
        return rows[:max_items_per_service]
    return rows


def download_wfs_layer(base_url: str, workspace: str, layer_name: str, output_dir: Path) -> bool:
    """Download WFS layer.

    Parameters
    ----------
    base_url : str
        Base URL for the request.
    workspace : str
        Workspace name to inspect.
    layer_name : str
        Layer name to inspect.
    output_dir : Path
        Directory where output files should be written.

    Returns
    -------
    bool
        True when the download succeeded.
    """
    try:
        import geopandas as gpd
    except Exception as exc:
        raise SystemExit(
            "WFS-download heeft geopandas nodig. Installeer eerst environment.yml."
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{sanitize_name(layer_name)}.gpkg"
    if output_path.exists() and not OVERSCHRIJF_BESTAANDE_BESTANDEN:
        return False

    url = (
        f"{base_url}/{workspace}/wfs?service=WFS&version=2.0.0&request=GetFeature"
        f"&typename={quote_plus(layer_name)}&outputFormat=application/json"
    )
    dataframe = gpd.read_file(url)
    dataframe.to_file(output_path, driver="GPKG")
    return True


def download_wcs_coverage(wcs_base_url: str, coverage_id: str, output_dir: Path) -> bool:
    """Download WCS coverage.

    Parameters
    ----------
    wcs_base_url : str
        Base URL for the WCS service.
    coverage_id : str
        Coverage identifier to download.
    output_dir : Path
        Directory where output files should be written.

    Returns
    -------
    bool
        True when the download succeeded.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{sanitize_name(coverage_id)}.tif"
    if output_path.exists() and not OVERSCHRIJF_BESTAANDE_BESTANDEN:
        return False

    if WCS_VERSIE == "2.0.1":
        params = {
            "service": "WCS",
            "request": "GetCoverage",
            "version": "2.0.1",
            "coverageId": coverage_id,
            "format": "image/geotiff",
            "outputCRS": "EPSG:28992",
        }
    else:
        params = {
            "service": "WCS",
            "request": "GetCoverage",
            "version": "1.0.0",
            "coverage": coverage_id,
            "format": "GeoTIFF",
        }

    response = requests.get(
        f"{wcs_base_url}/wcs",
        params=params,
        timeout=TIMEOUT_SEC,
        stream=True,
    )
    response.raise_for_status()
    with output_path.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)
    return True


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()

    base_url = get_base()
    wcs_base_url = base_url
    repo_root = Path(__file__).resolve().parents[1]
    output_root = repo_root / "output" / "liwo" / "bulk_download"
    output_root.mkdir(parents=True, exist_ok=True)
    download_types = [value for value in DOWNLOAD_TYPES]
    workspaces_filter = WORKSPACES[:]
    alleen_scenario_lagen = ALLEEN_SCENARIO_LAGEN
    max_items_per_service = MAX_ITEMS_PER_SERVICE

    if SMOKE_MODE:
        download_types = ["wfs", "wcs"]
        workspaces_filter = ["LIWO_Basis"]
        alleen_scenario_lagen = False
        max_items_per_service = 1
        log("Smoke mode actief: eerste WFS-laag uit LIWO_Basis en eerste WCS coverage.")

    if "wms" in download_types:
        raise SystemExit(
            "WMS staat bewust niet in DOWNLOAD_TYPES. "
            "WMS is view-only en levert geen brondata-download; gebruik WFS of WCS."
        )

    valid_types = {"wfs", "wcs"}
    invalid = [value for value in download_types if value not in valid_types]
    if invalid:
        raise SystemExit(f"Onbekende DOWNLOAD_TYPES: {invalid}")

    workspaces = workspaces_filter[:] if workspaces_filter else discover_workspaces(base_url)
    summary: dict[str, dict[str, int]] = {}

    if "wfs" in download_types:
        summary["wfs"] = {
            "planned": 0,
            "downloaded": 0,
            "skipped_existing": 0,
            "skipped_smoke": 0,
            "failed": 0,
        }
        for workspace in workspaces:
            layer_names = take_items(
                list_wfs_layers(base_url, workspace, alleen_scenario_lagen),
                max_items_per_service,
            )
            summary["wfs"]["planned"] += len(layer_names)
            log(f"WFS {workspace}: {len(layer_names)} lagen gepland")
            if SMOKE_MODE:
                summary["wfs"]["skipped_smoke"] += len(layer_names)
                continue
            for layer_name in iter_with_progress(layer_names, f"WFS {workspace}", "laag"):
                try:
                    wrote = download_wfs_layer(
                        base_url,
                        workspace,
                        layer_name,
                        output_root / "wfs" / workspace,
                    )
                    if wrote:
                        summary["wfs"]["downloaded"] += 1
                        log(f"WFS gedownload: {layer_name}")
                    else:
                        summary["wfs"]["skipped_existing"] += 1
                        log(f"WFS overgeslagen (bestaat al): {layer_name}")
                except Exception as exc:
                    summary["wfs"]["failed"] += 1
                    log(f"WFS download mislukt voor {layer_name}: {exc}")

    if "wcs" in download_types:
        summary["wcs"] = {
            "planned": 0,
            "downloaded": 0,
            "skipped_existing": 0,
            "skipped_smoke": 0,
            "failed": 0,
        }
        coverage_ids = take_items(
            list_wcs_coverages(
                wcs_base_url,
                WCS_VERSIE,
                [] if SMOKE_MODE else workspaces_filter,
                alleen_scenario_lagen,
            ),
            max_items_per_service,
        )
        summary["wcs"]["planned"] = len(coverage_ids)
        log(f"WCS: {len(coverage_ids)} coverages gepland")
        if SMOKE_MODE:
            summary["wcs"]["skipped_smoke"] = len(coverage_ids)
            coverage_ids = []
        for coverage_id in iter_with_progress(coverage_ids, "WCS", "coverage"):
            workspace = coverage_id.split("__", 1)[0] if "__" in coverage_id else "unknown"
            try:
                wrote = download_wcs_coverage(
                    wcs_base_url,
                    coverage_id,
                    output_root / "wcs" / workspace,
                )
                if wrote:
                    summary["wcs"]["downloaded"] += 1
                    log(f"WCS gedownload: {coverage_id}")
                else:
                    summary["wcs"]["skipped_existing"] += 1
                    log(f"WCS overgeslagen (bestaat al): {coverage_id}")
            except Exception as exc:
                summary["wcs"]["failed"] += 1
                log(f"WCS download mislukt voor {coverage_id}: {exc}")

    summary_path = output_root / "bulk_download_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print_json_block(
        "LIWO bulk download samenvatting:",
        {
            "download_types": download_types,
            "workspace_count": len(workspaces),
            "output_root": str(output_root),
            "summary_file": str(summary_path),
            "summary": summary,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
