#!/usr/bin/env python3
"""Download één bestand uit één LDO-scenario.

Gebruik dit script om gericht een scenario-bestand lokaal op te halen.
Zet bovenin het scenario-ID en de bestandsnaam die je wilt downloaden.
"""

from __future__ import annotations

import os
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
)

# Instellingen
BASE_URL = get_base()
SCENARIO_ID = 20069
BESTANDSNAAM = "Mortality.tif"  # Laat leeg om automatisch eerste bestand te pakken
PAK_EERSTE_BESTAND_ALS_LEEG = True
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"


def choose_file_name(scenario: dict, explicit_name: str, use_first_file: bool) -> str:
    """Choose the file name to download for a scenario.

    Parameters
    ----------
    scenario : dict
        Scenario payload to inspect.
    explicit_name : str
        Explicit file name requested by the user.
    use_first_file : bool
        Whether the first available file may be used as a fallback.

    Returns
    -------
    str
        Text result.
    """
    if explicit_name:
        return explicit_name
    files = scenario.get("files", {}) if isinstance(scenario, dict) else {}
    names = sorted(files.keys()) if isinstance(files, dict) else []
    if use_first_file and names:
        return str(names[0])
    raise SystemExit(
        "Zet BESTANDSNAAM in het script of zet PAK_EERSTE_BESTAND_ALS_LEEG = True."
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
    session = make_session(token)
    scenario_resp = session.get(
        api_url(BASE_URL, f"scenarios/{SCENARIO_ID}"), timeout=60
    )
    scenario_resp.raise_for_status()
    scenario = scenario_resp.json()

    file_name = choose_file_name(scenario, BESTANDSNAAM, PAK_EERSTE_BESTAND_ALS_LEEG)
    if SMOKE_MODE:
        print_json_block(
            "Download samenvatting:",
            {
                "scenario_id": SCENARIO_ID,
                "file_name": file_name,
                "smoke_mode": True,
                "download_skipped": True,
            },
        )
        return 0

    signed_resp = session.get(
        api_url(
            BASE_URL,
            f"scenarios/{SCENARIO_ID}/files/{quote(file_name, safe='')}/download",
        ),
        timeout=60,
    )
    signed_resp.raise_for_status()
    signed_url = signed_resp.json().get("url", "")
    if not signed_url:
        raise SystemExit("No signed URL returned by API.")

    out_path = output_file(f"scenario_{SCENARIO_ID}_{file_name}")

    # Signed URLs are external (S3) and should be requested without LDO auth headers.
    with requests.get(signed_url, stream=True, timeout=180) as download_resp:
        download_resp.raise_for_status()
        with out_path.open("wb") as f:
            for chunk in download_resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    print_json_block(
        "Download samenvatting:",
        {
            "scenario_id": SCENARIO_ID,
            "file_name": file_name,
            "size_bytes": out_path.stat().st_size if out_path.exists() else 0,
        },
    )
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
