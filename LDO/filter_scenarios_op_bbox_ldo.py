#!/usr/bin/env python3
"""Filter LDO-scenario's op RD New bounding box.

Gebruik dit script om alleen scenario's in een interessegebied te selecteren.
Je past bovenin de bbox-grenzen aan en krijgt een gefilterde CSV.
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
BBOX_MIN_X = 0.0
BBOX_MIN_Y = 300000.0
BBOX_MAX_X = 300000.0
BBOX_MAX_Y = 630000.0
MAX_CONSOLE_ROWS = 200


def in_bbox(x: float, y: float, minx: float, miny: float, maxx: float, maxy: float) -> bool:
    """Return whether a coordinate falls inside the bbox.

    Parameters
    ----------
    x : float
        X-coordinate value.
    y : float
        Y-coordinate value.
    minx : float
        Minimum x bound.
    miny : float
        Minimum y bound.
    maxx : float
        Maximum x bound.
    maxy : float
        Maximum y bound.

    Returns
    -------
    bool
        True when the check succeeds.
    """
    return minx <= x <= maxx and miny <= y <= maxy


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
    total = 0
    with_coords = 0

    for scenario in iter_scenarios(
        session=session,
        base=BASE_URL,
        limit=PAGINA_GROOTTE,
        max_scenarios=MAX_AANTAL_SCENARIOS,
    ):
        total += 1
        meta = scenario.get("meta", {}) if isinstance(scenario, dict) else {}
        x = to_float(
            meta_value(
                meta,
                "x-coordinaten doorbraaklocatie/effectgebied",
                "x-coordinaten doorbraaklocatie",
            )
        )
        y = to_float(
            meta_value(
                meta,
                "y-coordinaten doorbraaklocatie/effectgebied",
                "y-coordinaten doorbraaklocatie",
            )
        )
        if x is None or y is None:
            continue
        with_coords += 1
        if in_bbox(x, y, BBOX_MIN_X, BBOX_MIN_Y, BBOX_MAX_X, BBOX_MAX_Y):
            rows.append(
                {
                    "scenario_id": str(scenario.get("id", "")),
                    "status": str(scenario.get("status", "")),
                    "scenario_type": str(scenario.get("scenario_type", "")),
                    "scenarionaam": meta_value(meta, "scenarionaam"),
                    "x_rdnew": str(x),
                    "y_rdnew": str(y),
                }
            )

    out_path = output_file("ldo_scenarios_in_bbox.csv")
    write_csv(
        out_path,
        rows,
        ["scenario_id", "status", "scenario_type", "scenarionaam", "x_rdnew", "y_rdnew"],
    )

    print("Scenario's in bbox:")
    print_table(
        rows,
        [
            ("scenario_id", "scenario_id", 10),
            ("status", "status", 10),
            ("x_rdnew", "x_rdnew", 14),
            ("y_rdnew", "y_rdnew", 14),
            ("scenarionaam", "scenarionaam", 45),
        ],
        MAX_CONSOLE_ROWS,
    )
    print("")
    print_json_block(
        "BBox-samenvatting:",
        {
            "bbox": {
                "min_x": BBOX_MIN_X,
                "min_y": BBOX_MIN_Y,
                "max_x": BBOX_MAX_X,
                "max_y": BBOX_MAX_Y,
            },
            "scenarios_scanned": total,
            "scenarios_with_coordinates": with_coords,
            "scenarios_in_bbox": len(rows),
        },
    )
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
