#!/usr/bin/env python3
"""Controleer basisrechten van je LDO token op één scenario en één bestand."""

from __future__ import annotations

import base64
import json

from _ldo_common import (
    api_url,
    get_base,
    get_token,
    load_env_fallback,
    make_session,
    print_json_block,
)

# Instellingen
SCENARIO_ID = 20069
BESTANDSNAAM = "AB2-125X_BRES_05-Maximale_overstromingsdiepte-17_run01_0048.tiff"
TIMEOUT_SEC = 30


def decode_jwt_claims(token: str) -> dict:
    """Decode the claims section of a JWT token.

    Parameters
    ----------
    token : str
        Bearer token used for authenticated requests.

    Returns
    -------
    dict
        Result dictionary.
    """
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
    raw = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
    return json.loads(raw)


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()

    base_url = get_base()
    token = get_token(required=True)
    session = make_session(token)

    scenario_response = session.get(
        api_url(base_url, f"scenarios/{SCENARIO_ID}"),
        timeout=TIMEOUT_SEC,
    )
    file_options_response = session.options(
        api_url(base_url, f"scenarios/{SCENARIO_ID}/files/{BESTANDSNAAM}"),
        timeout=TIMEOUT_SEC,
    )

    scenario_status = ""
    scenario_name = ""
    if scenario_response.ok:
        payload = scenario_response.json()
        scenario_status = str(payload.get("status", ""))
        scenario_name = str(payload.get("name", ""))

    print_json_block(
        "LDO permissions check:",
        {
            "scenario_id": SCENARIO_ID,
            "bestand": BESTANDSNAAM,
            "scenario_get_status_code": scenario_response.status_code,
            "scenario_status": scenario_status,
            "scenario_name": scenario_name,
            "file_options_status_code": file_options_response.status_code,
            "file_allowed_methods": file_options_response.headers.get("Allow", ""),
            "jwt_claims": decode_jwt_claims(token),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
