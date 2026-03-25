#!/usr/bin/env python3
"""
Maak een CSV met per scenario:
- gekozen metadata-velden
- vaste bestandsgroottes (bytes) + totale grootte

Het script is standalone:
1) downloadt eerst zelf de LDO export-xlsx
2) gebruikt die xlsx om scenario-IDs op te halen
3) vraagt per scenario de file sizes op via de API
"""

from __future__ import annotations

import math
import os
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
from tqdm import tqdm

from _ldo_common import get_base, load_env_fallback


SCRIPT_FILE = Path(__file__).resolve()
REPO_ROOT = SCRIPT_FILE.parents[1]
load_env_fallback()

# Config
EXPORT_XLSX = REPO_ROOT / "output" / "ldo" / "metadata" / "01_interm_all_scenarios.xlsx"
OUTPUT_CSV = REPO_ROOT / "output" / "ldo" / "investigation" / "scenario_filesizes_summary.csv"
OUTPUT_ERRORS_CSV = REPO_ROOT / "output" / "ldo" / "investigation" / "scenario_filesizes_errors.csv"
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"
SMOKE_MAX_SCENARIOS = int(os.getenv("LIWO_LDO_SMOKE_MAX_SCENARIOS", "120"))

EXCEL_HEADER_ROW = 1
EXCEL_SKIP_ROWS = [2, 3, 4]

EXCEL_COL_SCENARIO_ID = "Nummer"
EXCEL_COLS_WANTED = [
    "Scenarionaam",
    "Scenariotype",
    "Scenariodatum",
    "Eigenaar Overstromingsinformatie",
    "x-coordinaten doorbraaklocatie/effectgebied",
    "y-coordinaten doorbraaklocatie/effectgebied",
    "Naam doorbraaklocatie",
    "Gebiedsnaam",
]

BASE = get_base()
TOKEN = os.getenv("LDO_TOKEN", "")
HEADERS = {"accept": "application/json", "authorization": f"Bearer {TOKEN}"}

EXPORT_TIMEOUT_SEC = int(os.getenv("LDO_EXPORT_TIMEOUT_SEC", "180"))
EXPORT_RETRIES = int(os.getenv("LDO_EXPORT_RETRIES", "3"))
REQUEST_TIMEOUT_CONNECT = int(os.getenv("LDO_REQUEST_CONNECT_TIMEOUT_SEC", "5"))
REQUEST_TIMEOUT_READ = int(os.getenv("LDO_REQUEST_READ_TIMEOUT_SEC", "30"))


def mb(n_bytes: int | None) -> float | None:
    """Convert bytes to megabytes.

    Parameters
    ----------
    n_bytes : int | None
        Size in bytes.

    Returns
    -------
    float | None
        Floating-point result.
    """
    if n_bytes is None or (isinstance(n_bytes, float) and math.isnan(n_bytes)):
        return None
    return round(n_bytes / (1024.0 * 1024.0), 2)


def _is_valid_xlsx(path: Path) -> bool:
    """Return whether valid Excel.

    Parameters
    ----------
    path : Path
        Target path for this operation.

    Returns
    -------
    bool
        True when the check succeeds.
    """
    try:
        with zipfile.ZipFile(path, "r") as zf:
            return "[Content_Types].xml" in zf.namelist()
    except Exception:
        return False


def download_export_xlsx(target: Path) -> None:
    """Download export Excel.

    Parameters
    ----------
    target : Path
        Target path for the downloaded file.
    """
    url = f"{BASE}/scenarios/export"
    payload = {"id": [], "mode": "public"}
    target.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None

    for attempt in range(1, max(1, EXPORT_RETRIES) + 1):
        tmp = target.with_suffix(f"{target.suffix}.part")
        try:
            with requests.post(
                url,
                headers=HEADERS,
                json=payload,
                stream=True,
                timeout=(10, EXPORT_TIMEOUT_SEC),
            ) as response:
                response.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)

            if not _is_valid_xlsx(tmp):
                raise RuntimeError("Downloaded export is not a valid xlsx file.")

            tmp.replace(target)
            print(f"Downloaded export: {target}")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(attempt)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    if target.exists() and _is_valid_xlsx(target):
        print(f"Warning: using existing valid export after retries: {target}")
        return

    raise RuntimeError(f"Failed to download export to {target}") from last_error


def _pick(meta: dict, *keys: str):
    """Pick the first non-empty value for the requested keys.

    Parameters
    ----------
    meta : dict
        Metadata dictionary to search.
    *keys : str
        Candidate keys checked in order.

    Returns
    -------
    Any
        First non-empty matching value, or `None`.
    """
    if not isinstance(meta, dict):
        return None
    for key in keys:
        value = meta.get(key)
        if value not in ("", None):
            return value
    low = {str(k).lower(): v for k, v in meta.items()}
    for key in keys:
        value = low.get(key.lower())
        if value not in ("", None):
            return value
    return None


def _api_file_size(info: dict) -> int | None:
    """Return API file size.

    Parameters
    ----------
    info : dict
        File metadata dictionary.

    Returns
    -------
    int | None
        Integer result.
    """
    file_meta = info.get("file")
    if isinstance(file_meta, dict) and isinstance(file_meta.get("size"), int):
        return file_meta["size"]
    return None


def _range_get_content_length(url: str) -> int | None:
    """Return range get content length.

    Parameters
    ----------
    url : str
        URL to request.

    Returns
    -------
    int | None
        Integer result.
    """
    try:
        response = requests.get(
            url,
            headers={"Range": "bytes=0-0"},
            stream=True,
            timeout=(REQUEST_TIMEOUT_CONNECT, 20),
        )
        if response.status_code in (200, 206):
            content_range = response.headers.get("Content-Range")
            if content_range and "/" in content_range:
                return int(content_range.split("/")[-1])
    except Exception:
        pass
    return None


def _map_file_to_column(name: str, sid: int) -> str | None:
    """Map file to column.

    Parameters
    ----------
    name : str
        Name to sanitize or transform.
    sid : int
        Scenario identifier.

    Returns
    -------
    str | None
        Text result.
    """
    n = (name or "").strip().lower()
    if n == "mortality.tif":
        return "Mortality.tif"
    if n == "total_damage.tif":
        return "Total_damage.tif"
    if n == "total_victims.tif":
        return "Total_victims.tif"
    if n == "total_affected.tif":
        return "Total_affected.tif"
    if n == "gridmaxwaterdepth.zip":
        return "gridmaxwaterdepth.zip"
    if n == "gridmaxflowvelocity.zip":
        return "gridmaxflowvelocity.zip"
    if n == f"scenario_{sid}_max_velocity.tiff":
        return "scenario_id_max_velocity.tiff"
    if n == f"scenario_{sid}_max_waterdepth.tiff":
        return "scenario_id_max_waterdepth.tiff"
    return None


def _short_error(text: str, max_len: int = 180) -> str:
    """Shorten error.

    Parameters
    ----------
    text : str
        Text to trim.
    max_len : int
        Maximum output length.

    Returns
    -------
    str
        Text result.
    """
    clean = str(text).replace("\r", " ").replace("\n", " ").strip()
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3] + "..."


def print_console_summary(
    out: pd.DataFrame,
    file_cols: list[str],
    requested_scenarios: int,
    errors: list[dict[str, str]],
    elapsed_sec: float,
) -> None:
    """Print console summary.

    Parameters
    ----------
    out : pd.DataFrame
        Output mapping updated in place.
    file_cols : list[str]
        Configured output columns for file metadata.
    requested_scenarios : int
        Requested scenario identifiers.
    errors : list[dict[str, str]]
        Mutable list that collects error messages.
    elapsed_sec : float
        Elapsed processing time in seconds.
    """
    rows = len(out)
    total_bytes = int(pd.to_numeric(out["total_bytes"], errors="coerce").fillna(0).sum()) if rows else 0
    total_gb = round(total_bytes / (1024.0 * 1024.0 * 1024.0), 2)
    mean_mb = round(float(pd.to_numeric(out["total_megabytes"], errors="coerce").fillna(0).mean()), 2) if rows else 0.0
    median_mb = (
        round(float(pd.to_numeric(out["total_megabytes"], errors="coerce").fillna(0).median()), 2) if rows else 0.0
    )

    print("")
    print("Samenvatting:")
    print(f"- scenarios requested: {requested_scenarios}")
    print(f"- rows written: {rows}")
    print(f"- scenario errors: {len(errors)}")
    print(f"- total estimated size: {total_bytes} bytes ({total_gb} GB)")
    print(f"- avg/median scenario size: {mean_mb} MB / {median_mb} MB")
    print(f"- elapsed: {round(elapsed_sec, 1)} sec")

    if rows:
        print("")
        print("Dekking per bestandskolom:")
        coverage_rows = []
        for col in file_cols:
            present = int(out[col].notna().sum())
            pct = round((present / rows) * 100.0, 1) if rows else 0.0
            col_bytes = int(pd.to_numeric(out[col], errors="coerce").fillna(0).sum())
            col_gb = round(col_bytes / (1024.0 * 1024.0 * 1024.0), 2)
            coverage_rows.append(
                {
                    "bestand": col,
                    "aanwezig": present,
                    "dekking_pct": pct,
                    "totaal_gb": col_gb,
                }
            )
        print(pd.DataFrame(coverage_rows).to_string(index=False))

        top_cols = ["scenario_id", "Scenarionaam", "total_megabytes"]
        top = out[top_cols].copy()
        top["total_megabytes"] = pd.to_numeric(top["total_megabytes"], errors="coerce").fillna(0.0)
        top = top.sort_values("total_megabytes", ascending=False).head(10)
        print("")
        print("Top 10 grootste scenario's (MB):")
        print(top.to_string(index=False))

    if errors:
        print("")
        print("Voorbeelden van errors (eerste 10):")
        for item in errors[:10]:
            print(f"- scenario {item['scenario_id']}: {item['error']}")


def fetch_meta_and_sizes_row(session: requests.Session, sid: int) -> dict:
    """Build one combined metadata and size row.

    Parameters
    ----------
    session : requests.Session
        Authenticated requests session.
    sid : int
        Scenario identifier.

    Returns
    -------
    dict
        Result dictionary.
    """
    meta_cols = [
        "scenario_id",
        "Scenarionaam",
        "Scenariotype",
        "Eigenaar overstromingsinformatie",
        "Scenariodatum",
        "x-coordinaten doorbraaklocatie/effectgebied",
        "y-coordinaten doorbraaklocatie/effectgebied",
        "Naam buitenwater",
        "Naam doorbraaklocatie",
        "Gebiedsnaam",
    ]
    file_cols = [
        "Mortality.tif",
        "Total_damage.tif",
        "Total_victims.tif",
        "Total_affected.tif",
        "gridmaxwaterdepth.zip",
        "gridmaxflowvelocity.zip",
        "scenario_id_max_velocity.tiff",
        "scenario_id_max_waterdepth.tiff",
    ]
    row = {c: None for c in meta_cols + file_cols}
    row["scenario_id"] = int(sid)

    response = session.get(
        f"{BASE}/scenarios/{sid}",
        timeout=(REQUEST_TIMEOUT_CONNECT, REQUEST_TIMEOUT_READ),
    )
    response.raise_for_status()
    scenario = response.json()
    meta = scenario.get("meta", {}) or {}
    files = scenario.get("files", {}) or {}

    row["Scenarionaam"] = _pick(meta, "scenarionaam", "Scenarionaam")
    row["Scenariotype"] = _pick(meta, "scenariotype", "Scenariotype", "scenario type")
    row["Eigenaar overstromingsinformatie"] = _pick(
        meta, "eigenaar overstromingsinformatie", "Eigenaar overstromingsinformatie"
    )
    row["Scenariodatum"] = _pick(meta, "scenariodatum", "Scenariodatum")
    row["x-coordinaten doorbraaklocatie/effectgebied"] = _pick(
        meta,
        "x-coordinaten doorbraaklocatie/effectgebied",
        "x-coordinaten doorbraaklocatie",
    )
    row["y-coordinaten doorbraaklocatie/effectgebied"] = _pick(
        meta,
        "y-coordinaten doorbraaklocatie/effectgebied",
        "y-coordinaten doorbraaklocatie",
    )
    row["Naam buitenwater"] = _pick(meta, "naam buitenwater", "Naam buitenwater")
    row["Naam doorbraaklocatie"] = _pick(meta, "naam doorbraaklocatie", "Naam doorbraaklocatie")
    row["Gebiedsnaam"] = _pick(meta, "gebiedsnaam", "Gebiedsnaam")

    for name, info in files.items():
        col = _map_file_to_column(name, sid)
        if not col:
            continue
        size = _api_file_size(info)
        if size is None:
            presigned_resp = session.get(
                f"{BASE}/scenarios/{sid}/files/{quote(name, safe='')}/download",
                timeout=(REQUEST_TIMEOUT_CONNECT, REQUEST_TIMEOUT_READ),
            )
            if presigned_resp.ok:
                presigned = presigned_resp.json().get("url")
                if presigned:
                    size = _range_get_content_length(presigned)
        if size is not None:
            row[col] = size

    total_bytes = sum(
        value
        for key, value in row.items()
        if key in file_cols and isinstance(value, int)
    )
    row["total_bytes"] = total_bytes
    row["total_megabytes"] = mb(total_bytes)
    return row


def main() -> None:
    """Run the script and return an exit code."""
    started = time.perf_counter()
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    download_export_xlsx(EXPORT_XLSX)

    if not EXPORT_XLSX.exists():
        raise SystemExit(f"Export xlsx ontbreekt: {EXPORT_XLSX}")

    usecols = [EXCEL_COL_SCENARIO_ID] + EXCEL_COLS_WANTED
    df_x = pd.read_excel(
        EXPORT_XLSX,
        engine="openpyxl",
        header=EXCEL_HEADER_ROW,
        skiprows=EXCEL_SKIP_ROWS,
        usecols=lambda c: c in usecols,
    )

    if EXCEL_COL_SCENARIO_ID not in df_x.columns:
        raise RuntimeError(f"Kolom '{EXCEL_COL_SCENARIO_ID}' niet gevonden in Excel.")

    df_x = df_x.rename(columns={EXCEL_COL_SCENARIO_ID: "scenario_id"})
    df_x["scenario_id"] = pd.to_numeric(df_x["scenario_id"], errors="coerce").astype("Int64")
    df_x = df_x.dropna(subset=["scenario_id"]).copy()
    scenario_ids = df_x["scenario_id"].astype(int).unique().tolist()

    if SMOKE_MODE:
        scenario_ids = scenario_ids[:SMOKE_MAX_SCENARIOS]

    meta_cols = [
        "scenario_id",
        "Scenarionaam",
        "Scenariotype",
        "Eigenaar overstromingsinformatie",
        "Scenariodatum",
        "x-coordinaten doorbraaklocatie/effectgebied",
        "y-coordinaten doorbraaklocatie/effectgebied",
        "Naam buitenwater",
        "Naam doorbraaklocatie",
        "Gebiedsnaam",
    ]
    file_cols = [
        "Mortality.tif",
        "Total_damage.tif",
        "Total_victims.tif",
        "Total_affected.tif",
        "gridmaxwaterdepth.zip",
        "gridmaxflowvelocity.zip",
        "scenario_id_max_velocity.tiff",
        "scenario_id_max_waterdepth.tiff",
    ]

    session = requests.Session()
    session.headers.update(HEADERS)
    wide_rows = []
    errors: list[dict[str, str]] = []

    print(f"Scenarios to process: {len(scenario_ids)}")

    for sid in tqdm(scenario_ids, desc="Meta + filesizes"):
        try:
            wide_rows.append(fetch_meta_and_sizes_row(session, int(sid)))
        except Exception as exc:
            errors.append({"scenario_id": str(sid), "error": _short_error(str(exc))})
            empty_row = {c: None for c in meta_cols + file_cols}
            empty_row["scenario_id"] = int(sid)
            empty_row["total_bytes"] = 0
            empty_row["total_megabytes"] = 0.0
            wide_rows.append(empty_row)

    session.close()

    output_cols = meta_cols + file_cols + ["total_bytes", "total_megabytes"]
    out = pd.DataFrame(wide_rows, columns=output_cols)
    out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    pd.DataFrame(errors, columns=["scenario_id", "error"]).to_csv(OUTPUT_ERRORS_CSV, index=False, encoding="utf-8-sig")

    elapsed = time.perf_counter() - started
    print_console_summary(
        out=out,
        file_cols=file_cols,
        requested_scenarios=len(scenario_ids),
        errors=errors,
        elapsed_sec=elapsed,
    )
    print(f"Geschreven: {OUTPUT_CSV}")
    print(f"Geschreven errors: {OUTPUT_ERRORS_CSV}")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Missing LDO_TOKEN. Put it in .env first.")
    main()
