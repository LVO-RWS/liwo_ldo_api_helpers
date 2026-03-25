#!/usr/bin/env python3
"""Exporteer een compacte CSV van LDO-scenario's.

Gebruik dit script om scenario-overzicht op te halen voor analyse.
Je kunt onderaan sturen op paginagrootte en maximaal aantal scenario's.
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
PAGINA_GROOTTE = 200
MAX_AANTAL_SCENARIOS = 0  # 0 = alles
MAX_CONSOLE_ROWS = 20


def to_row(item: dict) -> dict[str, str]:
    """Convert one item to an output row.

    Parameters
    ----------
    item : dict
        Item to convert.

    Returns
    -------
    dict[str, str]
        Result dictionary.
    """
    meta = item.get("meta", {}) if isinstance(item, dict) else {}
    return {
        "id": str(item.get("id", "")),
        "status": str(item.get("status", "")),
        "scenario_type": str(item.get("scenario_type", "")),
        "scenarionaam": str(meta.get("scenarionaam", "")),
        "projectnaam": str(meta.get("projectnaam", "")),
        "owner": str(meta.get("eigenaar overstromingsinformatie", "")),
    }


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
    rows = [
        to_row(item)
        for item in iter_scenarios(
            session=session,
            base=BASE_URL,
            limit=PAGINA_GROOTTE,
            max_scenarios=MAX_AANTAL_SCENARIOS,
            mode_public=True,
            timeout=60,
        )
        if isinstance(item, dict)
    ]

    out_path = output_file("alle_scenarios_ldo.csv")
    write_csv(
        out_path,
        rows,
        ["id", "status", "scenario_type", "scenarionaam", "projectnaam", "owner"],
    )

    print("Voorbeeld scenario-overzicht:")
    print_table(
        rows,
        [
            ("id", "id", 8),
            ("status", "status", 12),
            ("scenario_type", "type", 18),
            ("scenarionaam", "scenarionaam", 42),
            ("owner", "owner", 30),
        ],
        MAX_CONSOLE_ROWS,
    )
    print("")
    print_json_block(
        "Samenvatting:",
        {
            "total_scenarios": len(rows),
            "shown_rows": min(len(rows), MAX_CONSOLE_ROWS if MAX_CONSOLE_ROWS > 0 else len(rows)),
        },
    )
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
