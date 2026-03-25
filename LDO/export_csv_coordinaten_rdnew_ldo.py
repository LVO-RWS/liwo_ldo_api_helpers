#!/usr/bin/env python3
"""Exporteer RD New coördinaten van LDO-scenario's.

Gebruik dit script om scenario-locaties in GIS of analyses te gebruiken.
De output bevat ook een vlag of coördinaten valide zijn.
"""

from __future__ import annotations

from _ldo_common import (
    get_base,
    get_token,
    iter_scenarios,
    load_env_fallback,
    make_session,
    meta_value,
    output_file,
    print_json_block,
    print_table,
    to_float,
    write_csv,
)

# Instellingen
BASE_URL = get_base()
PAGINA_GROOTTE = 200
MAX_AANTAL_SCENARIOS = 0  # 0 = alles
MAX_CONSOLE_ROWS = 20


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
    rows: list[dict[str, str]] = []
    valid = 0
    total = 0

    for scenario in iter_scenarios(
        session=session,
        base=BASE_URL,
        limit=PAGINA_GROOTTE,
        max_scenarios=MAX_AANTAL_SCENARIOS,
    ):
        meta = scenario.get("meta", {}) if isinstance(scenario, dict) else {}
        total += 1
        x_raw = meta_value(
            meta,
            "x-coordinaten doorbraaklocatie/effectgebied",
            "x-coordinaten doorbraaklocatie",
        )
        y_raw = meta_value(
            meta,
            "y-coordinaten doorbraaklocatie/effectgebied",
            "y-coordinaten doorbraaklocatie",
        )
        x = to_float(x_raw)
        y = to_float(y_raw)
        is_valid = x is not None and y is not None
        if is_valid:
            valid += 1
        rows.append(
            {
                "scenario_id": str(scenario.get("id", "")),
                "status": str(scenario.get("status", "")),
                "scenario_type": str(scenario.get("scenario_type", "")),
                "scenarionaam": meta_value(meta, "scenarionaam"),
                "x_rdnew": "" if x is None else str(x),
                "y_rdnew": "" if y is None else str(y),
                "has_valid_coordinates": "1" if is_valid else "0",
            }
        )

    csv_path = output_file("ldo_scenario_coordinates_rdnew.csv")
    write_csv(
        csv_path,
        rows,
        [
            "scenario_id",
            "status",
            "scenario_type",
            "scenarionaam",
            "x_rdnew",
            "y_rdnew",
            "has_valid_coordinates",
        ],
    )

    valid_rows = [row for row in rows if row["has_valid_coordinates"] == "1"]
    print("Voorbeeld geldige coördinaten:")
    print_table(
        valid_rows,
        [
            ("scenario_id", "scenario_id", 10),
            ("status", "status", 12),
            ("x_rdnew", "x_rdnew", 14),
            ("y_rdnew", "y_rdnew", 14),
            ("scenarionaam", "scenarionaam", 45),
        ],
        MAX_CONSOLE_ROWS,
    )
    print("")
    print_json_block(
        "Coordinaten-samenvatting:",
        {
            "scenarios_processed": total,
            "valid_coordinates": valid,
            "invalid_coordinates": max(0, total - valid),
        },
    )
    print(f"Wrote: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
