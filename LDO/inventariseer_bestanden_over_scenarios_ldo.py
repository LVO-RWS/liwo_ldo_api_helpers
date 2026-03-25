#!/usr/bin/env python3
"""Inventariseer bestanden over veel LDO-scenario's.

Gebruik dit script om bestandsnamen, types en aantallen over scenario's te vergelijken.
Handig voor analytics op beschikbare data en volume.
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from _ldo_common import (
    api_url,
    get_base,
    get_token,
    iter_scenarios,
    load_env_fallback,
    make_session,
    output_file,
    print_json_block,
    print_table,
    write_csv,
    write_json,
)

# Instellingen
BASE_URL = get_base()
PAGINA_GROOTTE = 200
MAX_AANTAL_SCENARIOS = 0  # 0 = alles
AANTAL_WORKERS = 8
REQUEST_TIMEOUT_SEC = 60
MAX_CONSOLE_ROWS = 20
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"
SMOKE_MAX_AANTAL_SCENARIOS = 100


def fetch_scenario_files(
    session,
    base: str,
    scenario_id: int,
    timeout: int,
) -> tuple[int, list[dict[str, Any]], str]:
    """Fetch the files for one scenario.

    Parameters
    ----------
    session : Any
        Authenticated requests session.
    base : str
        Base URL for the request.
    scenario_id : int
        Scenario identifier.
    timeout : int
        Timeout in seconds.

    Returns
    -------
    tuple[int, list[dict[str, Any]], str]
        Tuple with the requested values.
    """
    try:
        response = session.get(api_url(base, f"scenarios/{scenario_id}"), timeout=timeout)
        response.raise_for_status()
        scenario = response.json()
        files = scenario.get("files", {}) if isinstance(scenario, dict) else {}
        rows: list[dict[str, Any]] = []
        for name, info in files.items():
            if not isinstance(info, dict):
                info = {}
            file_meta = info.get("file", {}) if isinstance(info.get("file"), dict) else {}
            rows.append(
                {
                    "scenario_id": str(scenario_id),
                    "file_name": str(name),
                    "file_type": str(info.get("type", "")),
                    "is_user_input": str(info.get("is_user_input", "")),
                    "size_bytes": str(file_meta.get("size", "")),
                }
            )
        return scenario_id, rows, ""
    except Exception as exc:
        return scenario_id, [], str(exc)


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
    max_aantal_scenarios = SMOKE_MAX_AANTAL_SCENARIOS if SMOKE_MODE else MAX_AANTAL_SCENARIOS

    if SMOKE_MODE:
        print(f"Smoke mode actief: maximaal {max_aantal_scenarios} scenario's")

    scenario_ids = [
        int(item.get("id"))
        for item in iter_scenarios(
            session=session,
            base=BASE_URL,
            limit=PAGINA_GROOTTE,
            max_scenarios=max_aantal_scenarios,
        )
        if str(item.get("id", "")).isdigit()
    ]

    inventory_rows: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    file_name_counter: Counter[str] = Counter()
    file_type_counter: Counter[str] = Counter()
    size_by_name: defaultdict[str, int] = defaultdict(int)

    with ThreadPoolExecutor(max_workers=max(1, AANTAL_WORKERS)) as executor:
        futures = {
            executor.submit(
                fetch_scenario_files,
                session,
                BASE_URL,
                scenario_id,
                REQUEST_TIMEOUT_SEC,
            ): scenario_id
            for scenario_id in scenario_ids
        }
        for future in as_completed(futures):
            scenario_id = futures[future]
            sid, rows, error = future.result()
            if error:
                errors.append({"scenario_id": str(sid), "error": error})
                continue
            inventory_rows.extend(rows)
            for row in rows:
                file_name = row["file_name"]
                file_type = row["file_type"]
                file_name_counter[file_name] += 1
                file_type_counter[file_type] += 1
                try:
                    size_by_name[file_name] += int(row["size_bytes"])
                except Exception:
                    pass

    inventory_csv = output_file("ldo_files_inventory.csv")
    file_name_csv = output_file("ldo_file_name_counts.csv")
    file_type_csv = output_file("ldo_file_type_counts.csv")
    top_size_csv = output_file("ldo_file_name_total_size_bytes.csv")
    errors_csv = output_file("ldo_files_inventory_errors.csv")
    summary_json = output_file("ldo_files_inventory_summary.json")

    write_csv(
        inventory_csv,
        sorted(inventory_rows, key=lambda row: (row["scenario_id"], row["file_name"])),
        ["scenario_id", "file_name", "file_type", "is_user_input", "size_bytes"],
    )
    write_csv(
        file_name_csv,
        [
            {"file_name": key, "count": str(count)}
            for key, count in sorted(file_name_counter.items(), key=lambda i: (-i[1], i[0]))
        ],
        ["file_name", "count"],
    )
    write_csv(
        file_type_csv,
        [
            {"file_type": key, "count": str(count)}
            for key, count in sorted(file_type_counter.items(), key=lambda i: (-i[1], i[0]))
        ],
        ["file_type", "count"],
    )
    write_csv(
        top_size_csv,
        [
            {"file_name": key, "total_size_bytes": str(total)}
            for key, total in sorted(size_by_name.items(), key=lambda i: (-i[1], i[0]))
        ],
        ["file_name", "total_size_bytes"],
    )
    write_csv(errors_csv, errors, ["scenario_id", "error"])
    write_json(
        summary_json,
        {
            "scenarios_requested": len(scenario_ids),
            "rows": len(inventory_rows),
            "errors": len(errors),
            "unique_file_names": len(file_name_counter),
            "unique_file_types": len(file_type_counter),
        },
    )

    top_file_names = [
        {"file_name": key, "count": str(count)}
        for key, count in sorted(file_name_counter.items(), key=lambda i: (-i[1], i[0]))
    ]
    top_file_types = [
        {"file_type": key, "count": str(count)}
        for key, count in sorted(file_type_counter.items(), key=lambda i: (-i[1], i[0]))
    ]
    print("Top bestandsnamen:")
    print_table(top_file_names, [("file_name", "file_name", 45), ("count", "count", 8)], MAX_CONSOLE_ROWS)
    print("")
    print("Bestandstypen:")
    print_table(top_file_types, [("file_type", "file_type", 28), ("count", "count", 8)], MAX_CONSOLE_ROWS)
    print("")
    print_json_block(
        "Files-inventory samenvatting:",
        {
            "scenarios_requested": len(scenario_ids),
            "inventory_rows": len(inventory_rows),
            "errors": len(errors),
            "unique_file_names": len(file_name_counter),
            "unique_file_types": len(file_type_counter),
        },
    )
    print(f"Wrote: {inventory_csv}")
    print(f"Wrote: {summary_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
