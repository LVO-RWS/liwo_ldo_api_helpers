#!/usr/bin/env python3
"""Shared helper functions for simple LDO scripts."""

from __future__ import annotations

import csv
import inspect
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from openpyxl import Workbook


REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_RUN_STAMPS: dict[str, str] = {}


def _caller_script_path() -> Path | None:
    """Return the path of the first caller outside this helper module.

    Returns
    -------
    Path | None
        Path to the calling script, if one was found.
    """
    here = Path(__file__).resolve()
    for frame in inspect.stack()[1:]:
        filename = Path(frame.filename).resolve()
        if filename == here:
            continue
        return filename
    return None


def load_env_fallback() -> None:
    """Load environment variables from the nearest available `.env` file."""
    candidates: list[Path] = []
    caller = _caller_script_path()
    if caller is not None:
        candidates.extend(parent / ".env" for parent in caller.parents)
    candidates.append(REPO_ROOT / ".env")
    candidates.extend(parent / ".env" for parent in REPO_ROOT.parents)
    candidates.append(Path.cwd() / ".env")
    seen: set[str] = set()
    for env_path in candidates:
        key = str(env_path.resolve()) if env_path.exists() else str(env_path)
        if key in seen:
            continue
        seen.add(key)
        if not env_path.exists():
            continue
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            env_key, value = line.split("=", 1)
            env_key = env_key.strip()
            value = value.strip().strip('"').strip("'")
            if env_key:
                os.environ.setdefault(env_key, value)
        return


def get_base() -> str:
    """Return the configured base URL.

    Returns
    -------
    str
        Configured base URL.
    """
    load_env_fallback()
    base = os.getenv("LDO_BASE", "").strip()
    if not base:
        raise SystemExit("Missing LDO_BASE. Put it in .env first.")
    return base.rstrip("/")


def get_liwo_base() -> str:
    """Return the configured LIWO base URL.

    Returns
    -------
    str
        Configured LIWO base URL.
    """
    load_env_fallback()
    base = os.getenv("LIWO_BASE", "").strip()
    if not base:
        raise SystemExit("Missing LIWO_BASE. Put it in .env first.")
    return base.rstrip("/")


def get_token(required: bool = True) -> str:
    """Return the configured LDO token.

    Parameters
    ----------
    required : bool
        Whether the value must be present.

    Returns
    -------
    str
        Configured LDO token.
    """
    load_env_fallback()
    token = os.getenv("LDO_TOKEN", "")
    if required and not token:
        raise SystemExit("Missing LDO_TOKEN. Put it in .env first.")
    return token


def make_session(token: str) -> requests.Session:
    """Create an authenticated LDO session.

    Parameters
    ----------
    token : str
        Bearer token used for authenticated requests.

    Returns
    -------
    requests.Session
        Authenticated requests session.
    """
    session = requests.Session()
    session.headers.update(
        {"accept": "application/json", "authorization": f"Bearer {token}"}
    )
    return session


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


def output_dir(*parts: str) -> Path:
    """Return the base output directory.

    Parameters
    ----------
    *parts : str
        Optional subdirectories inside the base output directory.

    Returns
    -------
    Path
        Base output directory.
    """
    path = REPO_ROOT / "output" / "ldo"
    if parts:
        path = path.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


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


def output_file(filename: str) -> Path:
    """Return a timestamped output file path.

    Parameters
    ----------
    filename : str
        File name to use.

    Returns
    -------
    Path
        Timestamped output file path.
    """
    stem = _caller_script_stem()
    stamp = _script_stamp(stem)
    clean_name = Path(filename).name
    return output_dir() / f"{stamp}_{stem}_{clean_name}"


def output_run_dir(dirname: str | None = None, *parts: str) -> Path:
    """Return a timestamped output directory.

    Parameters
    ----------
    dirname : str | None
        Optional name for the run directory.
    *parts : str
        Extra path components accepted by the helper.

    Returns
    -------
    Path
        Timestamped output directory path.
    """
    stem = _caller_script_stem()
    stamp = _script_stamp(stem)
    if dirname:
        clean_name = Path(dirname).name
        folder_name = f"{stamp}_{stem}_{clean_name}"
    else:
        folder_name = f"{stamp}_{stem}"
    path = output_dir(*parts) / folder_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_run_file(
    producer_script_stem: str,
    rel_filename: str,
    *parts: str,
) -> Path:
    """Return the newest matching output file.

    Parameters
    ----------
    producer_script_stem : str
        Script stem used to look up earlier outputs.
    rel_filename : str
        File name relative to a producer output.
    *parts : str
        Extra path components accepted for compatibility with this helper.

    Returns
    -------
    Path
        Newest matching output file path.
    """
    base = REPO_ROOT / "output" / "ldo"
    if not base.exists():
        return base / rel_filename
    candidates = sorted(base.glob(f"*_{producer_script_stem}_{Path(rel_filename).name}"))
    if not candidates:
        return base / rel_filename
    return candidates[-1]


def api_url(base: str, path: str) -> str:
    """Join a base URL and API path.

    Parameters
    ----------
    base : str
        Base URL for the request.
    path : str
        API path to append to the base URL.

    Returns
    -------
    str
        Combined request URL.
    """
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def write_json(path: Path, payload: Any) -> None:
    """Write a JSON payload to disk.

    Parameters
    ----------
    path : Path
        Target path for this operation.
    payload : Any
        Payload to write or print.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write rows to a CSV file.

    Parameters
    ----------
    path : Path
        Target path for this operation.
    rows : list[dict[str, Any]]
        Rows to write or print.
    fieldnames : list[str]
        Column names for the output.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_excel_workbook(
    path: Path,
    sheets: list[tuple[str, list[dict[str, Any]], list[str]]],
) -> None:
    """Write one or more worksheets to an Excel file.

    Parameters
    ----------
    path : Path
        Target path for this operation.
    sheets : list[tuple[str, list[dict[str, Any]], list[str]]]
        Worksheet definitions to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    used_titles: set[str] = set()

    def _sheet_title(name: str) -> str:
        """Build a safe Excel sheet title.

        Parameters
        ----------
        name : str
            Name to sanitize or transform.

        Returns
        -------
        str
            Safe worksheet title.
        """
        clean = "".join("_" if ch in '[]:*?/\\' else ch for ch in str(name)).strip()
        clean = clean or "Blad"
        base = clean[:31]
        title = base
        counter = 2
        while title in used_titles:
            suffix = f"_{counter}"
            title = f"{base[: 31 - len(suffix)]}{suffix}"
            counter += 1
        used_titles.add(title)
        return title

    for index, (sheet_name, rows, fieldnames) in enumerate(sheets):
        worksheet = workbook.active if index == 0 else workbook.create_sheet()
        worksheet.title = _sheet_title(sheet_name)
        worksheet.append(fieldnames)
        for row in rows:
            worksheet.append([row.get(fieldname, "") for fieldname in fieldnames])
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions

    workbook.save(path)


def write_excel(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
    sheet_name: str = "Overzicht",
) -> None:
    """Write rows to a single-sheet Excel file.

    Parameters
    ----------
    path : Path
        Target path for this operation.
    rows : list[dict[str, Any]]
        Rows to write or print.
    fieldnames : list[str]
        Column names for the output.
    sheet_name : str
        Worksheet name for the Excel output.
    """
    write_excel_workbook(path, [(sheet_name, rows, fieldnames)])


def print_json_block(title: str, payload: Any) -> None:
    """Print a titled JSON block.

    Parameters
    ----------
    title : str
        Title shown above the printed block.
    payload : Any
        Payload to write or print.
    """
    print(title)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def print_table(
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str, int]],
    max_rows: int = 20,
) -> None:
    """Print rows as an aligned plain-text table.

    Parameters
    ----------
    rows : list[dict[str, Any]]
        Rows to write or print.
    columns : list[tuple[str, str, int]]
        Column definitions for console output.
    max_rows : int
        Maximum number of rows to print.
    """
    if not rows:
        print("(geen rijen)")
        return

    if max_rows <= 0:
        shown = rows
    else:
        shown = rows[:max_rows]

    widths: dict[str, int] = {}
    for key, label, max_width in columns:
        data_width = max(len(str(row.get(key, "")).replace("\n", " / ")) for row in shown)
        widths[key] = max(len(label), min(max_width, data_width))

    def _fmt(value: Any, key: str) -> str:
        """Format one table cell for aligned console output.

        Parameters
        ----------
        value : Any
            Value to inspect or format.
        key : str
            Key for the value being formatted.

        Returns
        -------
        str
            Formatted cell text.
        """
        text = str(value).replace("\r", " ").replace("\n", " / ")
        width = widths[key]
        if len(text) > width:
            return text[: max(0, width - 3)] + "..."
        return text.ljust(width)

    header = " | ".join(_fmt(label, key) for key, label, _ in columns)
    sep = "-+-".join("-" * widths[key] for key, _, _ in columns)
    print(header)
    print(sep)
    for row in shown:
        print(" | ".join(_fmt(row.get(key, ""), key) for key, _, _ in columns))

    if len(rows) > len(shown):
        print(f"... {len(rows) - len(shown)} extra rijen (zie outputbestand).")


def meta_value(meta: dict[str, Any], *keys: str) -> str:
    """Return the first non-empty metadata value for the requested keys.

    Parameters
    ----------
    meta : dict[str, Any]
        Metadata dictionary to search.
    *keys : str
        Candidate keys checked in order.

    Returns
    -------
    str
        First non-empty matching metadata value.
    """
    if not isinstance(meta, dict):
        return ""
    for key in keys:
        if key in meta and meta.get(key) not in ("", None):
            return str(meta.get(key))
    lower_map = {str(k).lower(): v for k, v in meta.items()}
    for key in keys:
        value = lower_map.get(key.lower())
        if value not in ("", None):
            return str(value)
    return ""


def to_float(value: Any) -> float | None:
    """Convert a value to a float when possible.

    Parameters
    ----------
    value : Any
        Value to inspect or format.

    Returns
    -------
    float | None
        Parsed floating-point value, or `None` when parsing fails.
    """
    try:
        if value is None:
            return None
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def list_scenarios_page(
    session: requests.Session,
    base: str,
    limit: int,
    offset: int,
    mode_public: bool = True,
    timeout: int = 60,
) -> dict[str, Any]:
    """Fetch one page of scenarios from the LDO API.

    Parameters
    ----------
    session : requests.Session
        Authenticated requests session.
    base : str
        Base URL for the request.
    limit : int
        Maximum number of items to request per page.
    offset : int
        Pagination offset for the API request.
    mode_public : bool
        Whether to request only public scenarios.
    timeout : int
        Timeout in seconds.

    Returns
    -------
    dict[str, Any]
        Page payload with `items` and `total`.
    """
    limit = int(limit)
    offset = int(offset)
    variants: list[dict[str, Any]] = []
    params_a: dict[str, Any] = {"limit": limit, "offset": offset}
    if mode_public:
        params_a["mode"] = "public"
    variants.append(params_a)

    params_b: dict[str, Any] = {"limit": min(limit, 100), "offset": offset}
    if mode_public:
        params_b["mode"] = "public"
    variants.append(params_b)
    variants.append({"limit": min(limit, 100), "offset": offset})
    variants.append({"offset": offset, "mode": "public"})
    variants.append({"limit": min(limit, 100), "offset": offset})

    last_error: Exception | None = None
    for params in variants:
        try:
            response = session.get(api_url(base, "scenarios"), params=params, timeout=timeout)
            if response.status_code >= 400:
                response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                continue
            items = payload.get("items", [])
            if not isinstance(items, list):
                continue
            total = payload.get("total", len(items))
            return {"items": items, "total": total}
        except Exception as exc:
            last_error = exc
            continue

    if last_error:
        raise last_error
    return {"items": [], "total": 0}


def iter_scenarios(
    session: requests.Session,
    base: str,
    limit: int = 200,
    max_scenarios: int = 0,
    mode_public: bool = True,
    timeout: int = 60,
):
    """Yield scenarios page by page from the LDO API.

    Parameters
    ----------
    session : requests.Session
        Authenticated requests session.
    base : str
        Base URL for the request.
    limit : int
        Maximum number of items to request per page.
    max_scenarios : int
        Maximum number of scenarios to process. Use `0` for all.
    mode_public : bool
        Whether to request only public scenarios.
    timeout : int
        Timeout in seconds.

    Yields
    -------
    Any
        Yielded scenarios.
    """
    offset = 0
    yielded = 0
    while True:
        page = list_scenarios_page(
            session=session,
            base=base,
            limit=limit,
            offset=offset,
            mode_public=mode_public,
            timeout=timeout,
        )
        items = page["items"]
        if not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            yield item
            yielded += 1
            if max_scenarios > 0 and yielded >= max_scenarios:
                return
        offset += len(items)
        total = int(page.get("total", offset))
        if offset >= total:
            break
