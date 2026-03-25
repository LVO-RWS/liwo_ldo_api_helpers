#!/usr/bin/env python3
"""Zoek LDO-scenario's op metadata-inhoud.

Gebruik dit script om bijvoorbeeld alle scenario's te vinden waarin een
bepaalde metadata-sleutel een zoekterm bevat.
"""

from __future__ import annotations

from _ldo_common import (
    get_base,
    get_token,
    iter_scenarios,
    load_env_fallback,
    make_session,
    output_file,
    print_json_block,
    print_table,
    write_csv,
)

# Instellingen
BASE_URL = get_base()
META_SLEUTEL = "scenarionaam"
ZOEKTEKST = "maas"
PAGINA_GROOTTE = 200
MAX_AANTAL_SCENARIOS = 0  # 0 = alles
MAX_CONSOLE_ROWS = 20


def get_meta_value(meta: dict, key: str) -> str:
    """Return meta value.

    Parameters
    ----------
    meta : dict
        Metadata dictionary to search.
    key : str
        Key for the value being formatted.

    Returns
    -------
    str
        Meta value.
    """
    if not isinstance(meta, dict):
        return ""
    if key in meta:
        return str(meta.get(key, ""))
    low = {str(k).lower(): v for k, v in meta.items()}
    return str(low.get(key.lower(), ""))


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
    needle = ZOEKTEKST.lower()
    matches: list[dict[str, str]] = []
    scanned = 0

    for item in iter_scenarios(
        session=session,
        base=BASE_URL,
        limit=PAGINA_GROOTTE,
        max_scenarios=MAX_AANTAL_SCENARIOS,
        mode_public=True,
        timeout=60,
    ):
        if not isinstance(item, dict):
            continue
        scanned += 1
        meta = item.get("meta", {})
        value = get_meta_value(meta, META_SLEUTEL)
        if needle in value.lower():
            matches.append(
                {
                    "scenario_id": str(item.get("id", "")),
                    "status": str(item.get("status", "")),
                    "scenarionaam": str(meta.get("scenarionaam", "")),
                    "meta_key": META_SLEUTEL,
                    "meta_value": value,
                }
            )

    out_path = output_file("ldo_scenarios_meta_search.csv")
    write_csv(
        out_path,
        matches,
        ["scenario_id", "status", "scenarionaam", "meta_key", "meta_value"],
    )

    print("Gevonden matches:")
    print_table(
        matches,
        [
            ("scenario_id", "scenario_id", 10),
            ("status", "status", 12),
            ("scenarionaam", "scenarionaam", 45),
            ("meta_value", "meta_value", 50),
        ],
        MAX_CONSOLE_ROWS,
    )
    print("")
    print_json_block(
        "Zoek-samenvatting:",
        {
            "meta_sleutel": META_SLEUTEL,
            "zoektekst": ZOEKTEKST,
            "pagina_grootte": PAGINA_GROOTTE,
            "max_aantal_scenarios": MAX_AANTAL_SCENARIOS,
            "scanned_scenarios": scanned,
            "matches": len(matches),
            "shown_rows": min(len(matches), MAX_CONSOLE_ROWS if MAX_CONSOLE_ROWS > 0 else len(matches)),
        },
    )
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
