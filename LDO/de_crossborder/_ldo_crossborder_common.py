#!/usr/bin/env python3
"""Kleine helpers voor de LDO NL-DE crossborder use cases."""

from __future__ import annotations

import io
import inspect
import sys
import threading
import time
import zipfile
from datetime import datetime
from http.client import RemoteDisconnected
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

LDO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "LDO")
sys.path.insert(0, str(LDO_ROOT))

from _ldo_common import api_url, get_base, get_token, load_env_fallback, make_session

GEO_STACK_ERROR: Exception | None = None
try:
    import geopandas as gpd
    import numpy as np
    import rasterio
    from pyproj import CRS, Transformer
    from rasterio.mask import mask as rio_mask
    from rasterio.warp import transform_geom
    from shapely.geometry import Polygon, box, mapping, shape
    from shapely.ops import unary_union
except Exception as exc:  # pragma: no cover
    gpd = None
    np = None
    rasterio = None
    CRS = None
    Transformer = None
    rio_mask = None
    transform_geom = None
    Polygon = None
    box = None
    mapping = None
    shape = None
    unary_union = None
    GEO_STACK_ERROR = exc


REPO_ROOT = LDO_ROOT.parent
CROSSBORDER_DIR = Path(__file__).resolve().parent
CROSSBORDER_GADM_DIR = CROSSBORDER_DIR / "gadm"
CROSSBORDER_SRC_DIR = CROSSBORDER_GADM_DIR
CROSSBORDER_OUTPUT_DIR = REPO_ROOT / "output" / "ldo" / "de_crossborder"
NL_SHAPEFILE = CROSSBORDER_GADM_DIR / "gadm_NLD_shp" / "gadm41_NLD_0.shp"
DE_SHAPEFILE = CROSSBORDER_GADM_DIR / "gadm_DEU_shp" / "gadm41_DEU_1.shp"
RDNEW = CRS.from_epsg(28992) if CRS is not None else None
_SCRIPT_RUN_STAMPS: dict[str, str] = {}
_THREAD_LOCAL = threading.local()
CLASSIFY_RETRY_ATTEMPTS = 3
CLASSIFY_RETRY_BACKOFF_SEC = 1.0


def ensure_geo_stack() -> None:
    """Exit when the required geospatial packages are not available."""
    if GEO_STACK_ERROR is not None:
        raise SystemExit(
            "Geospatial packages ontbreken. Installeer eerst de omgeving uit environment.yml."
        ) from GEO_STACK_ERROR


def make_ldo_session() -> tuple[str, requests.Session]:
    """Create an authenticated LDO session and return it with the base URL.

    Returns
    -------
    tuple[str, requests.Session]
        Base URL and authenticated session.
    """
    load_env_fallback()
    base_url = get_base()
    token = get_token(required=True)
    return base_url, make_session(token)


def thread_local_ldo_session(token: str) -> requests.Session:
    """Reuse one authenticated LDO session per worker thread.

    Parameters
    ----------
    token : str
        Bearer token used for authenticated requests.

    Returns
    -------
    requests.Session
        Thread-local authenticated session.
    """
    session = getattr(_THREAD_LOCAL, "ldo_session", None)
    session_token = getattr(_THREAD_LOCAL, "ldo_session_token", None)
    if session is None or session_token != token:
        session = make_session(token)
        _THREAD_LOCAL.ldo_session = session
        _THREAD_LOCAL.ldo_session_token = token
    return session


def error_chain_text(exc: BaseException) -> str:
    """Return the combined error text from an exception and its causes.

    Parameters
    ----------
    exc : BaseException
        Exception to summarize.

    Returns
    -------
    str
        Combined lowercase error text.
    """
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).strip()
        if text:
            parts.append(text.lower())
        next_exc = current.__cause__ or current.__context__
        current = next_exc if isinstance(next_exc, BaseException) else None
    return " | ".join(parts)


def is_retryable_crossborder_error(exc: Exception) -> bool:
    """Return whether a crossborder scan error looks temporary.

    Parameters
    ----------
    exc : Exception
        Exception raised while fetching or scanning a scenario.

    Returns
    -------
    bool
        True when the error looks temporary and can be retried.
    """
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code in {408, 425, 429, 500, 502, 503, 504}:
        return True

    if isinstance(
        exc,
        (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            RemoteDisconnected,
        ),
    ):
        return True

    text = error_chain_text(exc)
    retry_markers = (
        "connection aborted",
        "connection reset",
        "connection refused",
        "remote disconnected",
        "remote end closed connection without response",
        "server disconnected",
        "temporary failure",
        "temporarily unavailable",
        "timed out",
        "timeout",
        "too many requests",
        "503",
        "502",
        "504",
        "429",
    )
    return any(marker in text for marker in retry_markers)


def _caller_script_stem() -> str:
    """Return the stem of the script that called this helper.

    Returns
    -------
    str
        Calling script stem, or `"script"` when no caller was found.
    """
    here = Path(__file__).resolve()
    for frame in inspect.stack()[1:]:
        filename = Path(frame.filename).resolve()
        if filename == here:
            continue
        return filename.stem
    return "script"


def _script_stamp(script_stem: str) -> str:
    """Return the cached timestamp for a script run.

    Parameters
    ----------
    script_stem : str
        Script stem used for the run-specific output name.

    Returns
    -------
    str
        Cached timestamp string for the given script.
    """
    if script_stem not in _SCRIPT_RUN_STAMPS:
        _SCRIPT_RUN_STAMPS[script_stem] = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _SCRIPT_RUN_STAMPS[script_stem]


def crossborder_output_base_dir() -> Path:
    """Return the base output directory for crossborder runs.

    Returns
    -------
    Path
        Base crossborder output directory.
    """
    CROSSBORDER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return CROSSBORDER_OUTPUT_DIR


def crossborder_run_dir(script_stem: str | None = None) -> Path:
    """Return the timestamped output directory for a crossborder run.

    Parameters
    ----------
    script_stem : str | None
        Script stem used for the run-specific output name.

    Returns
    -------
    Path
        Timestamped crossborder run directory.
    """
    stem = script_stem or _caller_script_stem()
    stamp = _script_stamp(stem)
    run_dir = crossborder_output_base_dir() / f"{stamp}_{stem}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def crossborder_output_file(filename: str, script_stem: str | None = None) -> Path:
    """Return an output file path inside the current crossborder run directory.

    Parameters
    ----------
    filename : str
        File name to use.
    script_stem : str | None
        Script stem used for the run-specific output name.

    Returns
    -------
    Path
        Output file path inside the current run directory.
    """
    return crossborder_run_dir(script_stem) / Path(filename).name


def latest_crossborder_run_dir(producer_script_stem: str) -> Path:
    """Return the newest output directory for a crossborder producer script.

    Parameters
    ----------
    producer_script_stem : str
        Script stem used to look up earlier outputs.

    Returns
    -------
    Path
        Newest matching run directory.
    """
    base_dir = crossborder_output_base_dir()
    candidates = sorted(
        path
        for path in base_dir.glob(f"*_{producer_script_stem}")
        if path.is_dir()
    )
    if not candidates:
        return base_dir / producer_script_stem
    return candidates[-1]


def latest_crossborder_file(producer_script_stem: str, filename: str) -> Path:
    """Return the newest named file produced by a crossborder script.

    Parameters
    ----------
    producer_script_stem : str
        Script stem used to look up earlier outputs.
    filename : str
        File name to use.

    Returns
    -------
    Path
        Newest matching output file.
    """
    return latest_crossborder_run_dir(producer_script_stem) / Path(filename).name


def download_gadm_shapefile(country_code: str, target_dir: Path, version: str = "4.1") -> Path:
    """Download and extract a GADM shapefile archive.

    Parameters
    ----------
    country_code : str
        ISO3 country code used by GADM.
    target_dir : Path
        Directory where the archive is extracted.
    version : str
        Dataset version to download.

    Returns
    -------
    Path
        Directory with the extracted shapefile archive.
    """
    url = (
        f"https://geodata.ucdavis.edu/gadm/gadm{version}/shp/"
        f"gadm{version.replace('.', '')}_{country_code}_shp.zip"
    )
    response = requests.get(url, timeout=180)
    response.raise_for_status()
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        archive.extractall(target_dir)
    return target_dir


def download_all_scenarios_excel(
    session: requests.Session,
    base_url: str,
    output_path: Path,
) -> Path:
    """Download the official Excel export with all LDO scenarios.

    Parameters
    ----------
    session : requests.Session
        Authenticated requests session.
    base_url : str
        Base URL for the request.
    output_path : Path
        Output path for the downloaded file.

    Returns
    -------
    Path
        Path to the downloaded Excel export.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    response = session.post(
        api_url(base_url, "scenarios/export"),
        json={"id": [], "mode": "public"},
        timeout=180,
        stream=True,
    )
    response.raise_for_status()
    with output_path.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)
    return output_path


def read_export_metadata(export_path: Path) -> pd.DataFrame:
    """Read the Excel export and keep the metadata columns used in this workflow.

    Parameters
    ----------
    export_path : Path
        Downloaded Excel export to read.

    Returns
    -------
    pd.DataFrame
        Normalized scenario metadata table.
    """
    dataframe = pd.read_excel(export_path, header=1, skiprows=[2, 3, 4])
    normalized = {str(column).strip().lower(): column for column in dataframe.columns}
    wanted = {
        "nummer": "scenario_id",
        "scenarionaam": "scenarionaam",
        "projectnaam": "projectnaam",
        "eigenaar overstromingsinformatie": "eigenaar",
        "naam buitenwater": "naam_buitenwater",
        "naam doorbraaklocatie": "naam_doorbraaklocatie",
        "x-coordinaten doorbraaklocatie/effectgebied": "x_rdnew",
        "y-coordinaten doorbraaklocatie/effectgebied": "y_rdnew",
    }
    selected: dict[str, pd.Series] = {}
    for source_name, target_name in wanted.items():
        original_name = normalized.get(source_name)
        if original_name is None:
            continue
        selected[target_name] = dataframe[original_name]

    compact = pd.DataFrame(selected)
    compact = compact[pd.notnull(compact.get("scenario_id"))].copy()
    compact["scenario_id"] = compact["scenario_id"].astype(int)
    return compact


def read_country_layers() -> tuple["gpd.GeoDataFrame", "gpd.GeoDataFrame"]:
    """Read the NL and DE boundary layers and project them to RD New.

    Returns
    -------
    tuple['gpd.GeoDataFrame', 'gpd.GeoDataFrame']
        Dutch and German boundary layers in RD New.
    """
    ensure_geo_stack()
    if not NL_SHAPEFILE.exists():
        raise SystemExit(f"Shapefile ontbreekt: {NL_SHAPEFILE}")
    if not DE_SHAPEFILE.exists():
        raise SystemExit(f"Shapefile ontbreekt: {DE_SHAPEFILE}")

    gdf_nl = gpd.read_file(NL_SHAPEFILE)
    gdf_de = gpd.read_file(DE_SHAPEFILE)
    if gdf_nl.crs is None:
        gdf_nl = gdf_nl.set_crs(epsg=4326)
    if gdf_de.crs is None:
        gdf_de = gdf_de.set_crs(epsg=4326)
    return gdf_nl.to_crs(RDNEW), gdf_de.to_crs(RDNEW)


def find_depth_tif_url(
    session: requests.Session,
    base_url: str,
    scenario_id: int,
    depth_hint: str = "Maximale_overstromingsdiepte",
) -> tuple[str | None, str | None]:
    """Find the best matching depth TIFF for a scenario and return its download URL.

    Parameters
    ----------
    session : requests.Session
        Authenticated requests session.
    base_url : str
        Base URL for the request.
    scenario_id : int
        Scenario identifier.
    depth_hint : str
        Preferred marker used to choose the depth raster.

    Returns
    -------
    tuple[str | None, str | None]
        Selected TIFF name and temporary download URL.
    """
    scenario_response = session.get(
        api_url(base_url, f"scenarios/{scenario_id}"),
        timeout=60,
    )
    scenario_response.raise_for_status()
    scenario_payload = scenario_response.json()
    files = scenario_payload.get("files", {})
    if not isinstance(files, dict):
        return None, None

    candidates: list[tuple[int, str]] = []
    for file_name, file_info in files.items():
        if not isinstance(file_info, dict):
            continue
        file_name_lower = str(file_name).lower()
        file_type_lower = str(file_info.get("type", "")).lower()
        looks_like_tif = file_name_lower.endswith((".tif", ".tiff")) or any(
            marker in file_type_lower for marker in ("tif", "tiff", "geotiff", "raster")
        )
        if not looks_like_tif:
            continue

        score = 0
        if depth_hint and depth_hint.lower() in file_name_lower:
            score += 2
        if "diepte" in file_name_lower or "depth" in file_name_lower:
            score += 1
        candidates.append((score, str(file_name)))

    if not candidates:
        return None, None

    candidates.sort(key=lambda item: (-item[0], item[1]))
    chosen_name = candidates[0][1]
    download_response = session.get(
        api_url(base_url, f"scenarios/{scenario_id}/files/{quote(chosen_name, safe='')}/download"),
        timeout=60,
    )
    download_response.raise_for_status()
    download_payload = download_response.json()
    return chosen_name, str(download_payload.get("url", "")).strip() or None


def bounds_polygon_from_dataset(dataset, target_crs=RDNEW):
    """Build a bounds polygon from an open raster dataset.

    Parameters
    ----------
    dataset : Any
        Open raster dataset to inspect.
    target_crs : Any
        CRS for the returned bounds geometry.

    Returns
    -------
    Any
        Raster bounds polygon.
    """
    ensure_geo_stack()
    left, bottom, right, top = dataset.bounds
    source_crs = dataset.crs if dataset.crs else CRS.from_epsg(4326)
    if CRS.from_user_input(source_crs) == target_crs:
        return box(left, bottom, right, top)

    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    ring = [
        (left, bottom),
        (right, bottom),
        (right, top),
        (left, top),
        (left, bottom),
    ]
    transformed = [transformer.transform(x_value, y_value) for x_value, y_value in ring]
    return Polygon(transformed)


def bounds_polygon_from_tif_url(url: str):
    """Build a bounds polygon from a raster URL.

    Parameters
    ----------
    url : str
        URL to request.

    Returns
    -------
    Any
        Raster bounds polygon.
    """
    ensure_geo_stack()
    with rasterio.open(url) as dataset:
        return bounds_polygon_from_dataset(dataset, target_crs=RDNEW)


def depth_stats_in_dataset(
    dataset,
    geom,
    geom_crs,
    min_positive: float = 0.00000001,
) -> dict[str, int]:
    """Count valid and positive raster pixels inside a geometry from an open dataset.

    Parameters
    ----------
    dataset : Any
        Open raster dataset to inspect.
    geom : Any
        Geometry used for clipping or intersection checks.
    geom_crs : Any
        CRS of the supplied geometry.
    min_positive : float
        Minimum raster value counted as positive.

    Returns
    -------
    dict[str, int]
        Counts of valid and positive pixels.
    """
    ensure_geo_stack()
    geom_shape = mapping(geom)
    geom_in_raster_crs = transform_geom(
        geom_crs.to_string(),
        dataset.crs.to_string(),
        geom_shape,
        precision=6,
    )
    if not shape(geom_in_raster_crs).intersects(box(*dataset.bounds)):
        return {"valid_count": 0, "positive_count": 0}

    array, _ = rio_mask(dataset, [geom_in_raster_crs], crop=True, filled=False)
    band = array[0]
    if band.mask.all():
        return {"valid_count": 0, "positive_count": 0}

    valid = ~band.mask
    valid_count = int(valid.sum())
    if valid_count == 0:
        return {"valid_count": 0, "positive_count": 0}

    values = band.data[valid]
    positive_count = int(np.sum(values > min_positive))
    return {"valid_count": valid_count, "positive_count": positive_count}


def depth_stats_in_geom(url: str, geom, geom_crs, min_positive: float = 0.00000001) -> dict[str, int]:
    """Count valid and positive raster pixels inside a geometry from a raster URL.

    Parameters
    ----------
    url : str
        URL to request.
    geom : Any
        Geometry used for clipping or intersection checks.
    geom_crs : Any
        CRS of the supplied geometry.
    min_positive : float
        Minimum raster value counted as positive.

    Returns
    -------
    dict[str, int]
        Counts of valid and positive pixels.
    """
    ensure_geo_stack()
    with rasterio.open(url) as dataset:
        return depth_stats_in_dataset(
            dataset,
            geom,
            geom_crs,
            min_positive=min_positive,
        )


def classify_scenario_for_de_crossborder(
    *,
    base_url: str,
    token: str,
    scenario_id: int,
    de_geom,
    nl_geom,
    geom_crs,
    depth_hint: str = "Maximale_overstromingsdiepte",
    min_positive_depth: float = 0.00000001,
    min_positive_pixels: int = 50,
    retry_attempts: int = CLASSIFY_RETRY_ATTEMPTS,
    retry_backoff_sec: float = CLASSIFY_RETRY_BACKOFF_SEC,
) -> dict[str, object]:
    """Classify one scenario as `CROSS_BORDER`, `DE_ONLY`, or no DE hit.

    Parameters
    ----------
    base_url : str
        Base URL for the request.
    token : str
        Bearer token used for authenticated requests.
    scenario_id : int
        Scenario identifier.
    de_geom : Any
        Merged geometry for the German area of interest.
    nl_geom : Any
        Merged geometry for the Dutch area of interest.
    geom_crs : Any
        CRS of the supplied geometry.
    depth_hint : str
        Preferred marker used to choose the depth raster.
    min_positive_depth : float
        Minimum raster value counted as positive depth.
    min_positive_pixels : int
        Minimum positive pixel count required for a match.
    retry_attempts : int
        Maximum number of attempts for temporary network errors.
    retry_backoff_sec : float
        Base wait time in seconds before a retry.

    Returns
    -------
    dict[str, object]
        Classification result and raster statistics.
    """
    ensure_geo_stack()
    attempts = max(1, int(retry_attempts))
    base_backoff = max(0.0, float(retry_backoff_sec))

    for attempt in range(1, attempts + 1):
        session = thread_local_ldo_session(token)
        try:
            tif_name, tif_url = find_depth_tif_url(
                session=session,
                base_url=base_url,
                scenario_id=scenario_id,
                depth_hint=depth_hint,
            )
            if not tif_url:
                return {
                    "scenario_id": scenario_id,
                    "status": "missing_tif",
                    "attempts": attempt,
                }

            with rasterio.open(tif_url) as dataset:
                bounds = bounds_polygon_from_dataset(dataset, target_crs=geom_crs)
                if not bounds.intersects(de_geom):
                    return {
                        "scenario_id": scenario_id,
                        "status": "outside_de_bounds",
                        "attempts": attempt,
                    }

                stats_de = depth_stats_in_dataset(
                    dataset,
                    de_geom,
                    geom_crs,
                    min_positive=min_positive_depth,
                )
                if stats_de["positive_count"] < int(min_positive_pixels):
                    return {
                        "scenario_id": scenario_id,
                        "status": "no_positive_de",
                        "de_valid": stats_de["valid_count"],
                        "de_positive": stats_de["positive_count"],
                        "attempts": attempt,
                    }

                stats_nl = depth_stats_in_dataset(
                    dataset,
                    nl_geom,
                    geom_crs,
                    min_positive=min_positive_depth,
                )
        except Exception as exc:
            retryable = is_retryable_crossborder_error(exc)
            if retryable and attempt < attempts:
                time.sleep(base_backoff * (2 ** (attempt - 1)))
                continue
            return {
                "scenario_id": scenario_id,
                "status": "error",
                "error": str(exc),
                "attempts": attempt,
                "retryable": retryable,
            }

        category = (
            "CROSS_BORDER"
            if stats_nl["positive_count"] >= int(min_positive_pixels)
            else "DE_ONLY"
        )
        return {
            "scenario_id": scenario_id,
            "status": category.lower(),
            "attempts": attempt,
            "row": {
                "scenario_id": scenario_id,
                "category": category,
                "tif_name": tif_name or "",
                "tif_url": tif_url,
                "de_valid": stats_de["valid_count"],
                "de_positive": stats_de["positive_count"],
                "nl_valid": stats_nl["valid_count"],
                "nl_positive": stats_nl["positive_count"],
            },
        }

    return {
        "scenario_id": scenario_id,
        "status": "error",
        "error": "Onbekende fout zonder resultaat.",
        "attempts": attempts,
        "retryable": False,
    }


def download_file(url: str, destination: Path, timeout: int = 300) -> Path:
    """Download a remote file to disk.

    Parameters
    ----------
    url : str
        URL to request.
    destination : Path
        Destination path for the download.
    timeout : int
        Timeout in seconds.

    Returns
    -------
    Path
        Downloaded file path.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    return destination
