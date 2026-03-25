#!/usr/bin/env python3
"""Download alle bestanden van één LDO-scenario.

Gebruik dit script als je in één keer alle files van een scenario wilt ophalen.
Het script schrijft ook een manifest-CSV met wat er succesvol is gedownload.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

import requests

from _ldo_common import (
    api_url,
    get_base,
    get_token,
    load_env_fallback,
    make_session,
    output_file,
    print_json_block,
    print_table,
    write_csv,
)

# Instellingen
BASE_URL = get_base()
SCENARIO_ID = 20069
REQUEST_TIMEOUT_SEC = 60
DOWNLOAD_TIMEOUT_SEC = 180
STOP_BIJ_EERSTE_FOUT = False
MAX_CONSOLE_ROWS = 25
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()

    token = get_token(required=True)
    session = make_session(token)
    scenario_resp = session.get(
        api_url(BASE_URL, f"scenarios/{SCENARIO_ID}"),
        timeout=REQUEST_TIMEOUT_SEC,
    )
    scenario_resp.raise_for_status()
    scenario = scenario_resp.json()
    files = scenario.get("files", {}) if isinstance(scenario, dict) else {}
    if not isinstance(files, dict) or not files:
        raise SystemExit(f"Geen files gevonden voor scenario {SCENARIO_ID}.")

    if SMOKE_MODE:
        manifest_csv = output_file(f"scenario_{SCENARIO_ID}_download_manifest.csv")
        errors_csv = output_file(f"scenario_{SCENARIO_ID}_download_errors.csv")
        planned_rows = []
        for file_name in sorted(files.keys()):
            file_info = files.get(file_name, {})
            if not isinstance(file_info, dict):
                file_info = {}
            api_file_meta = file_info.get("file", {}) if isinstance(file_info.get("file"), dict) else {}
            planned_rows.append(
                {
                    "scenario_id": str(SCENARIO_ID),
                    "file_name": str(file_name),
                    "file_type": str(file_info.get("type", "")),
                    "is_user_input": str(file_info.get("is_user_input", "")),
                    "size_bytes_api": str(api_file_meta.get("size", "")),
                    "size_bytes_downloaded": "",
                    "output_path": "",
                }
            )
        write_csv(
            manifest_csv,
            planned_rows,
            [
                "scenario_id",
                "file_name",
                "file_type",
                "is_user_input",
                "size_bytes_api",
                "size_bytes_downloaded",
                "output_path",
            ],
        )
        write_csv(errors_csv, [], ["file_name", "error"])
        print_json_block(
            "Download samenvatting:",
            {
                "scenario_id": SCENARIO_ID,
                "files_in_scenario": len(files),
                "downloaded": 0,
                "errors": 0,
                "smoke_mode": True,
                "download_skipped": len(planned_rows),
                "manifest_csv": str(manifest_csv),
                "errors_csv": str(errors_csv),
            },
        )
        print(f"Wrote: {manifest_csv}")
        print(f"Wrote: {errors_csv}")
        return 0

    downloaded_rows: list[dict[str, str]] = []
    error_rows: list[dict[str, str]] = []

    for file_name in sorted(files.keys()):
        file_info = files.get(file_name, {})
        if not isinstance(file_info, dict):
            file_info = {}
        api_file_meta = file_info.get("file", {}) if isinstance(file_info.get("file"), dict) else {}

        try:
            signed_resp = session.get(
                api_url(
                    BASE_URL,
                    f"scenarios/{SCENARIO_ID}/files/{quote(str(file_name), safe='')}/download",
                ),
                timeout=REQUEST_TIMEOUT_SEC,
            )
            signed_resp.raise_for_status()
            signed_url = signed_resp.json().get("url", "")
            if not signed_url:
                raise RuntimeError("Geen signed URL in response.")

            safe_name = Path(str(file_name)).name
            out_path = output_file(f"scenario_{SCENARIO_ID}_{safe_name}")

            # Signed URL staat buiten LDO API; daarom zonder auth headers downloaden.
            with requests.get(signed_url, stream=True, timeout=DOWNLOAD_TIMEOUT_SEC) as download_resp:
                download_resp.raise_for_status()
                with out_path.open("wb") as f:
                    for chunk in download_resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)

            downloaded_rows.append(
                {
                    "scenario_id": str(SCENARIO_ID),
                    "file_name": str(file_name),
                    "file_type": str(file_info.get("type", "")),
                    "is_user_input": str(file_info.get("is_user_input", "")),
                    "size_bytes_api": str(api_file_meta.get("size", "")),
                    "size_bytes_downloaded": str(out_path.stat().st_size if out_path.exists() else 0),
                    "output_path": str(out_path),
                }
            )
        except Exception as exc:
            error_rows.append({"file_name": str(file_name), "error": str(exc)})
            if STOP_BIJ_EERSTE_FOUT:
                raise

    manifest_csv = output_file(f"scenario_{SCENARIO_ID}_download_manifest.csv")
    errors_csv = output_file(f"scenario_{SCENARIO_ID}_download_errors.csv")
    write_csv(
        manifest_csv,
        downloaded_rows,
        [
            "scenario_id",
            "file_name",
            "file_type",
            "is_user_input",
            "size_bytes_api",
            "size_bytes_downloaded",
            "output_path",
        ],
    )
    write_csv(errors_csv, error_rows, ["file_name", "error"])

    print("Gedownloade bestanden:")
    print_table(
        downloaded_rows,
        [
            ("file_name", "file_name", 42),
            ("file_type", "file_type", 20),
            ("size_bytes_downloaded", "size_bytes", 12),
            ("is_user_input", "user_input", 10),
        ],
        MAX_CONSOLE_ROWS,
    )
    print("")
    print_json_block(
        "Download samenvatting:",
        {
            "scenario_id": SCENARIO_ID,
            "files_in_scenario": len(files),
            "downloaded": len(downloaded_rows),
            "errors": len(error_rows),
            "manifest_csv": str(manifest_csv),
            "errors_csv": str(errors_csv),
        },
    )
    print(f"Wrote: {manifest_csv}")
    print(f"Wrote: {errors_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
