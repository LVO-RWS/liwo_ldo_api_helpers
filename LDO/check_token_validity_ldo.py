#!/usr/bin/env python3
"""Controleer de geldigheid van het LDO token uit `.env`."""

from __future__ import annotations

import base64
import datetime as dt
import json
import os

from _ldo_common import load_env_fallback, print_json_block


def decode_jwt_payload(token: str) -> dict:
    """Decode the payload section of a JWT token.

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
    return json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")))


def describe_token(token_name: str, token: str) -> dict[str, object]:
    """Summarize the key properties of a token.

    Parameters
    ----------
    token_name : str
        Label used for the token in console output.
    token : str
        Bearer token used for authenticated requests.

    Returns
    -------
    dict[str, object]
        Result dictionary.
    """
    if not token:
        return {"token_name": token_name, "present": False}

    try:
        payload = decode_jwt_payload(token)
        issued_at = dt.datetime.fromtimestamp(payload["iat"], dt.UTC)
        expires_at = dt.datetime.fromtimestamp(payload["exp"], dt.UTC)
        remaining = expires_at - dt.datetime.now(dt.UTC)
        return {
            "token_name": token_name,
            "present": True,
            "issued_at_utc": issued_at.isoformat(),
            "expires_at_utc": expires_at.isoformat(),
            "remaining": str(remaining),
            "tenant": payload.get("tenant"),
            "sub": payload.get("sub"),
        }
    except Exception as exc:
        return {
            "token_name": token_name,
            "present": True,
            "error": str(exc),
        }


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()

    token = os.getenv("LDO_TOKEN", "")
    rows = [describe_token("ldo_token", token)]

    print_json_block("LDO token validity:", {"items": rows})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
