#!/usr/bin/env python3
"""Download de officiële LDO Excel-export met alle scenario's.

Gebruik dit script als startpunt voor analyses in Excel of pandas.
De export wordt rechtstreeks vanaf de API opgeslagen als .xlsx.
"""

from __future__ import annotations

import os

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
BESTANDSNAAM = "ldo_scenarios_export.xlsx"
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()

    out_path = output_file(BESTANDSNAAM)
    if SMOKE_MODE:
        print_json_block(
            "Export samenvatting:",
            {
                "smoke_mode": True,
                "download_skipped": True,
                "bestand": str(out_path),
            },
        )
        return 0

    token = get_token(required=True)
    session = make_session(token)

    payload = {"id": [], "mode": "public"}
    response = session.post(
        api_url(BASE_URL, "scenarios/export"),
        json=payload,
        timeout=120,
        stream=True,
    )
    response.raise_for_status()

    with out_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    print_json_block(
        "Export samenvatting:",
        {
            "bestand": str(out_path),
            "size_bytes": out_path.stat().st_size if out_path.exists() else 0,
        },
    )
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
