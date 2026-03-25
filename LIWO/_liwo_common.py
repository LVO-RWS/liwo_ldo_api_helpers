#!/usr/bin/env python3
"""Shared helper functions for simple LIWO scripts."""

from __future__ import annotations

import csv
import inspect
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import requests


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
    base = os.getenv("LIWO_BASE", "").strip()
    if not base:
        raise SystemExit("Missing LIWO_BASE. Put it in .env first.")
    return base.rstrip("/")


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
    path = REPO_ROOT / "output" / "liwo"
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
    base = REPO_ROOT / "output" / "liwo"
    if not base.exists():
        return base / rel_filename
    candidates = sorted(base.glob(f"*_{producer_script_stem}_{Path(rel_filename).name}"))
    if not candidates:
        return base / rel_filename
    return candidates[-1]


def get_xml(url: str, params: dict[str, Any], timeout: int = 30) -> ET.Element:
    """Fetch and parse an XML response.

    Parameters
    ----------
    url : str
        URL to request.
    params : dict[str, Any]
        Query parameters for the request.
    timeout : int
        Timeout in seconds.

    Returns
    -------
    ET.Element
        Parsed XML root element.
    """
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return ET.fromstring(response.content)


def local_name(tag: str) -> str:
    """Return the local name of an XML tag.

    Parameters
    ----------
    tag : str
        XML tag value to simplify.

    Returns
    -------
    str
        XML tag name without the namespace prefix.
    """
    return tag.split("}", 1)[-1] if "}" in tag else tag


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
