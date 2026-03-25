#!/usr/bin/env python3
"""Download geselecteerde WFS-lagen uit LIWO workspace `LIWO_Basis`.

Let op: dit is de huidige set downloadbare lagen in `LIWO_Basis`; controleer af en toe met `ontdek_services_liwo.py` of er nieuwe lagen zijn bijgekomen en werk deze lijst dan handmatig bij.
"""

from __future__ import annotations

import os
import re
from urllib.parse import quote_plus

from _liwo_common import get_base, load_env_fallback, output_file, print_json_block, write_json

# Instellingen
BASE_URL = get_base()
WORKSPACE = "LIWO_Basis"
OVERSCHRIJF_BESTAANDE_BESTANDEN = False
SMOKE_MODE = os.getenv("LIWO_LDO_SMOKE", "0") == "1"
SMOKE_MAX_LAYERS = int(os.getenv("LIWO_LDO_SMOKE_MAX_LAYERS", "1"))

# Comment of uncomment hier wat je wilt downloaden.
# Standaard staat alleen de huidige faalkans-laag aan.
BASISINFORMATIE_LAGEN = [
    "LIWO_Basis:overstromingskansen_actueel_2019_faalkans_primair",
    # "LIWO_Basis:Bovenregionale_stresstest_wateroverlast_Gevolgen",
    # "LIWO_Basis:HWBP_Programma_Kunstwerken",
    # "LIWO_Basis:administratieve_grenzen_gemeenten",
    # "LIWO_Basis:administratieve_grenzen_provincies",
    # "LIWO_Basis:administratieve_grenzen_regionale_onderdelen_rws",
    # "LIWO_Basis:administratieve_grenzen_veiligheidsregios",
    # "LIWO_Basis:administratieve_grenzen_waterschappen",
    # "LIWO_Basis:evac_droge_verdiepingen_gebouwen_nederland1",
    # "LIWO_Basis:evac_droge_verdiepingen_gebouwen_nederland2",
    # "LIWO_Basis:evac_droge_verdiepingen_gebouwen_nederland3",
    # "LIWO_Basis:evac_droge_verdiepingen_gebouwen_nederland4",
    # "LIWO_Basis:evac_droge_verdiepingen_gebouwen_nederland5",
    # "LIWO_Basis:evac_droge_verdiepingen_percentage_per_buurt_nederland1",
    # "LIWO_Basis:evac_droge_verdiepingen_percentage_per_buurt_nederland2",
    # "LIWO_Basis:evac_droge_verdiepingen_percentage_per_buurt_nederland3",
    # "LIWO_Basis:evac_droge_verdiepingen_percentage_per_buurt_nederland4",
    # "LIWO_Basis:evac_droge_verdiepingen_percentage_per_buurt_nederland5",
    # "LIWO_Basis:evac_kans_op_beschikbare_tijd_1dag",
    # "LIWO_Basis:evac_kans_op_beschikbare_tijd_2dag",
    # "LIWO_Basis:evac_kans_op_beschikbare_tijd_3dag",
    # "LIWO_Basis:evac_kans_op_beschikbare_tijd_4dag",
    # "LIWO_Basis:evac_kans_op_beschikbare_tijd_onverwacht",
    # "LIWO_Basis:evac_overstromingsduur",
    # "LIWO_Basis:evac_percentage_1dag",
    # "LIWO_Basis:evac_percentage_2dag",
    # "LIWO_Basis:evac_percentage_3dag",
    # "LIWO_Basis:evac_percentage_4dag",
    # "LIWO_Basis:evac_percentage_onverwacht",
    # "LIWO_Basis:evac_waarschuwingstijd",
    # "LIWO_Basis:evacuatie_evacuatiefractie_verwachtingswaarde",
    # "LIWO_Basis:gebiedsindeling_doorbraaklocaties_bovenregiostress",
    # "LIWO_Basis:gebiedsindeling_doorbraaklocaties_buitendijks",
    # "LIWO_Basis:gebiedsindeling_doorbraaklocaties_primair",
    # "LIWO_Basis:gebiedsindeling_doorbraaklocaties_regionaal",
    # "LIWO_Basis:gebiedsindeling_doorbraaklocaties_regionaalwatersysteem",
    # "LIWO_Basis:hwbp_programma_dijkvakken",
    # "LIWO_Basis:infrastructuur_dijkringen",
    # "LIWO_Basis:infrastructuur_niet_primaire_keringen",
    # "LIWO_Basis:infrastructuur_primaire_keringen",
    # "LIWO_Basis:infrastructuur_spoorwegen_nederland",
    # "LIWO_Basis:infrastructuur_vliegvelden_nederland",
    # "LIWO_Basis:infrastructuur_wegen_nederland",
    # "LIWO_Basis:overstromingskans_norm_2050_faalkans_traject_ondergrens",
    # "LIWO_Basis:overstromingskans_norm_2050_faalkans_traject_signalering",
    # "LIWO_Basis:overstromingskansen_actueel_2025_faalkans_primair_Limburg",
    # "LIWO_Basis:overstromingskansen_actueel_faalkans_niet_primair",
    # "LIWO_Basis:projectmatig_vastgesteld_risicokaart2019_buitengewoon",
    # "LIWO_Basis:projectmatig_vastgesteld_risicokaart2019_grote_kans",
    # "LIWO_Basis:projectmatig_vastgesteld_risicokaart2019_kleine_kans",
    # "LIWO_Basis:projectmatig_vastgesteld_risicokaart2019_middelgrote_kans",
    # "LIWO_Basis:versie_nummer",
]


def sanitize_name(value: str) -> str:
    """Sanitize a name for safe filesystem use.

    Parameters
    ----------
    value : str
        Value to inspect or format.

    Returns
    -------
    str
        Text result.
    """
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("_") or "item"


def build_wfs_url(layer_name: str) -> str:
    """Build WFS URL.

    Parameters
    ----------
    layer_name : str
        Layer name to inspect.

    Returns
    -------
    str
        Text result.
    """
    return (
        f"{BASE_URL}/{WORKSPACE}/wfs?service=WFS&version=2.0.0&request=GetFeature"
        f"&typename={quote_plus(layer_name)}&outputFormat=application/json"
    )


def main() -> int:
    """Run the script and return an exit code.

    Returns
    -------
    int
        Process exit code.
    """
    load_env_fallback()

    if not BASISINFORMATIE_LAGEN:
        raise SystemExit("Selecteer minstens één laag in BASISINFORMATIE_LAGEN.")

    selected_layers = BASISINFORMATIE_LAGEN[:SMOKE_MAX_LAYERS] if SMOKE_MODE else BASISINFORMATIE_LAGEN

    gpd = None
    if not SMOKE_MODE:
        try:
            import geopandas as gpd
        except Exception as exc:
            raise SystemExit(
                "Dit script heeft geopandas nodig. Installeer eerst de dependencies uit environment.yml."
            ) from exc

    rows: list[dict[str, str]] = []
    for layer_name in selected_layers:
        if not layer_name.startswith(f"{WORKSPACE}:"):
            raise SystemExit(f"Laag hoort niet bij workspace {WORKSPACE}: {layer_name}")

        short_name = layer_name.split(":", 1)[1]
        out_path = output_file(f"{sanitize_name(short_name)}.gpkg")
        row = {
            "workspace": WORKSPACE,
            "layer_name": layer_name,
            "output_path": str(out_path),
            "status": "skipped_existing",
            "rows": "",
            "crs": "",
            "error": "",
        }

        if out_path.exists() and not OVERSCHRIJF_BESTAANDE_BESTANDEN:
            print(f"Bestaat al, overgeslagen: {out_path}")
            rows.append(row)
            continue

        if SMOKE_MODE:
            row["status"] = "smoke_skipped"
            rows.append(row)
            continue

        print(f"Downloaden: {layer_name}")
        try:
            gdf = gpd.read_file(build_wfs_url(layer_name))
            gdf.to_file(out_path, driver="GPKG")
            row["status"] = "downloaded"
            row["rows"] = str(len(gdf))
            row["crs"] = str(gdf.crs)
            print(f"Wrote: {out_path}")
        except Exception as exc:
            row["status"] = "error"
            row["error"] = str(exc)
            print(f"Download mislukt voor {layer_name}: {exc}")

        rows.append(row)

    summary_path = output_file("basisinformatie_download_summary.json")
    write_json(
        summary_path,
        {
            "workspace": WORKSPACE,
            "selected_layers": selected_layers,
            "overwrite_existing": OVERSCHRIJF_BESTAANDE_BESTANDEN,
            "smoke_mode": SMOKE_MODE,
            "items": rows,
        },
    )

    print_json_block(
        "LIWO basisinformatie download samenvatting:",
        {
            "workspace": WORKSPACE,
            "selected_count": len(selected_layers),
            "downloaded": sum(1 for row in rows if row["status"] == "downloaded"),
            "skipped_existing": sum(1 for row in rows if row["status"] == "skipped_existing"),
            "smoke_skipped": sum(1 for row in rows if row["status"] == "smoke_skipped"),
            "errors": sum(1 for row in rows if row["status"] == "error"),
            "summary_file": str(summary_path),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
