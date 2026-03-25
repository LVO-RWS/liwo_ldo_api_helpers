#!/usr/bin/env python3
"""Exporteer een CSV met alle bestanden van één LDO-scenario.

Gebruik dit script om te zien welke bestanden bij een scenario horen,
inclusief type, user-input vlag en bestandsgrootte.
"""

from __future__ import annotations

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
MAX_CONSOLE_ROWS = 30


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
    response = session.get(api_url(BASE_URL, f"scenarios/{SCENARIO_ID}"), timeout=60)
    response.raise_for_status()
    scenario = response.json()
    files = scenario.get("files", {}) if isinstance(scenario, dict) else {}

    rows: list[dict[str, str]] = []
    for name, info in files.items():
        file_meta = info.get("file", {}) if isinstance(info, dict) else {}
        rows.append(
            {
                "scenario_id": str(SCENARIO_ID),
                "name": str(name),
                "type": str(info.get("type", "")),
                "is_user_input": str(info.get("is_user_input", "")),
                "size_bytes": str(file_meta.get("size", "")),
            }
        )

    out_path = output_file(f"scenario_{SCENARIO_ID}_files.csv")
    write_csv(
        out_path,
        sorted(rows, key=lambda r: r["name"]),
        ["scenario_id", "name", "type", "is_user_input", "size_bytes"],
    )

    rows_sorted = sorted(rows, key=lambda r: r["name"])

    print("Bestanden in scenario:")
    print_table(
        rows_sorted,
        [
            ("name", "name", 45),
            ("type", "type", 20),
            ("is_user_input", "user_input", 10),
            ("size_bytes", "size_bytes", 12),
        ],
        MAX_CONSOLE_ROWS,
    )
    print("")
    print_json_block(
        "Samenvatting:",
        {
            "scenario_id": SCENARIO_ID,
            "file_count": len(rows_sorted),
            "shown_rows": min(len(rows_sorted), MAX_CONSOLE_ROWS if MAX_CONSOLE_ROWS > 0 else len(rows_sorted)),
        },
    )
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
