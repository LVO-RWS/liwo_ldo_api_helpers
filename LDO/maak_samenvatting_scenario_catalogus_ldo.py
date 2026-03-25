#!/usr/bin/env python3
"""Maak een samenvatting van het compacte LDO scenario-overzicht.

Gebruik dit script na `export_csv_alle_scenarios_ldo.py`
om direct totalen per status, type en eigenaar te krijgen.
Het script gebruikt standaard de nieuwste overview-run.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from _ldo_common import (
    latest_run_file,
    output_file,
    print_json_block,
    print_table,
    write_csv,
    write_json,
)

# Instellingen
OVERZICHT_CSV_PAD = latest_run_file(
    "export_csv_alle_scenarios_ldo",
    "alle_scenarios_ldo.csv",
)


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read rows.

    Parameters
    ----------
    path : Path
        Target path for this operation.

    Returns
    -------
    list[dict[str, str]]
        Collected output rows.
    """
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def counter_rows(counter: Counter[str], key_name: str) -> list[dict[str, str]]:
    """Convert grouped counts to output rows.

    Parameters
    ----------
    counter : Counter[str]
        Counter with grouped totals.
    key_name : str
        Output column name for the grouped key.

    Returns
    -------
    list[dict[str, str]]
        Collected output rows.
    """
    return [
        {key_name: key, "count": str(count)}
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    overview_path = Path(OVERZICHT_CSV_PAD).resolve()
    if not overview_path.exists():
        raise SystemExit(
            f"Overview CSV not found: {overview_path}\n"
            "Run export_csv_alle_scenarios_ldo.py first."
        )

    rows = read_rows(overview_path)

    status_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    owner_counter: Counter[str] = Counter()
    status_type_counter: Counter[str] = Counter()

    for row in rows:
        status = row.get("status", "")
        scenario_type = row.get("scenario_type", "")
        owner = row.get("owner", "")
        status_counter[status] += 1
        type_counter[scenario_type] += 1
        owner_counter[owner] += 1
        status_type_counter[f"{status} | {scenario_type}"] += 1

    status_csv = output_file("summary_status_counts.csv")
    type_csv = output_file("summary_scenario_type_counts.csv")
    owner_csv = output_file("summary_owner_counts.csv")
    status_type_csv = output_file("summary_status_type_counts.csv")
    json_path = output_file("summary_overview.json")

    write_csv(status_csv, counter_rows(status_counter, "status"), ["status", "count"])
    write_csv(type_csv, counter_rows(type_counter, "scenario_type"), ["scenario_type", "count"])
    write_csv(owner_csv, counter_rows(owner_counter, "owner"), ["owner", "count"])
    write_csv(
        status_type_csv,
        counter_rows(status_type_counter, "status_and_type"),
        ["status_and_type", "count"],
    )
    write_json(
        json_path,
        {
            "rows": len(rows),
            "status_counts": dict(status_counter),
            "scenario_type_counts": dict(type_counter),
            "owner_counts": dict(owner_counter),
            "status_type_counts": dict(status_type_counter),
        },
    )

    print("Status verdeling:")
    print_table(counter_rows(status_counter, "status"), [("status", "status", 18), ("count", "count", 8)], 0)
    print("")
    print("Scenario type verdeling:")
    print_table(
        counter_rows(type_counter, "scenario_type"),
        [("scenario_type", "scenario_type", 24), ("count", "count", 8)],
        0,
    )
    print("")
    print("Top owners:")
    print_table(counter_rows(owner_counter, "owner"), [("owner", "owner", 35), ("count", "count", 8)], 15)
    print("")
    print_json_block(
        "Samenvatting:",
        {
            "source_overview_csv": str(overview_path),
            "rows": len(rows),
            "unique_statuses": len(status_counter),
            "unique_types": len(type_counter),
            "unique_owners": len(owner_counter),
        },
    )
    print(f"Wrote: {status_csv}")
    print(f"Wrote: {type_csv}")
    print(f"Wrote: {owner_csv}")
    print(f"Wrote: {status_type_csv}")
    print(f"Wrote: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
