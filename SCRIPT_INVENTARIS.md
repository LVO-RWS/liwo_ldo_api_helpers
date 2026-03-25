# Script Inventaris

## Doel

Deze repo draait nu op:

- scripts onder `LDO/` en `LIWO/`: uniforme scripts voor dagelijks gebruik door collega’s.

## LDO Scripts (`LDO`)

| Script | Use-case |
|---|---|
| `check_token_validity_ldo.py` | Geldigheid van `LDO_TOKEN` controleren |
| `check_permissions_ldo.py` | Snelle rechtencheck op scenario + bestand |
| `ontdek_api_structuur_ldo.py` | OpenAPI ophalen en endpoint-overzicht wegschrijven |
| `export_csv_alle_scenarios_ldo.py` | Compact scenario-overzicht als CSV exporteren |
| `download_excel_alle_scenarios_ldo.py` | Officiële scenario-export (`.xlsx`) downloaden |
| `inventariseer_ldo_velden.py` | Van één scenario alle veldpaden tonen, inclusief external processings |
| `export_csv_bestanden_per_scenario_ldo.py` | Files van één scenario als CSV |
| `download_bestand_van_scenario_ldo.py` | Eén file van een scenario downloaden |
| `download_alle_bestanden_van_scenario_ldo.py` | Alle files van één scenario downloaden |
| `batch_ldo_download_ldo.py` | Lijst scenario-ID's downloaden + één Excel-overzicht met alle gekozen velden |
| `zoek_scenarios_op_metadata_ldo.py` | Scenario’s zoeken op metadata sleutel/waarde |
| `maak_samenvatting_scenario_catalogus_ldo.py` | Samenvatting op status/type/eigenaar van de compacte scenario-export |
| `export_csv_coordinaten_rdnew_ldo.py` | RDNew coördinaten export |
| `filter_scenarios_op_bbox_ldo.py` | Selectie van scenario’s op RDNew bbox |
| `inventariseer_bestanden_over_scenarios_ldo.py` | Files inventory over meerdere scenario’s |
| `Investigation_File_Sizes_ALL_scens.py` | Inventarisatie van bestandsformaten en groottes over scenario’s |
| `vind_liwo_scenarios_in_ldo.py` | LIWO scenario-layers live ophalen en koppelen aan LDO IDs |
| `vind_mogelijk_nieuwere_liwo_scenarios_in_ldo.py` | Mogelijk nieuwere publieke LDO-varianten van LIWO-scenario’s zoeken |
| `de_crossborder/01_prepare_gadm_grensdata_crossborder_ldo.py` | NL/DE GADM grensdata downloaden |
| `de_crossborder/02_export_scenarios_grensoverschrijdend_ldo.py` | Excel-export + NL/NRW selectie, inclusief `scenarios_cross_border_and_de_only.csv` en `scenarios_cross_border_only.csv` |
| `de_crossborder/03_download_tiffs_grensscenarios_ldo.py` | GeoTIFFs van `CROSS_BORDER` + `DE_ONLY` scenario’s downloaden |
| `de_crossborder/04_plot_scenarios_nrw_crossborder_ldo.py` | `CROSS_BORDER` + `DE_ONLY` scenario’s op kaart zetten voor visuele controle |

## LIWO Scripts (`LIWO`)

| Script | Use-case |
|---|---|
| `ontdek_services_liwo.py` | Workspaces + WMS/WFS service-overzicht |
| `export_scenario_ids_per_workspace_liwo.py` | Scenario-layers per workspace exporteren |
| `export_wms_lagen_per_workspace_liwo.py` | Alle WMS-layers van één workspace |
| `download_wfs_laag_liwo.py` | Eén WFS layer naar GeoPackage |
| `download_basisinformatie_liwo.py` | Geselecteerde downloadbare WFS-lagen uit `LIWO_Basis` downloaden |
| `download_alle_lagen_liwo.py` | Bulk-download van WFS/WCS via één script |
| `export_wcs_coverages_liwo.py` | WCS coverage IDs (2.0.1 + 1.0.0) |
| `download_wcs_coverage_liwo.py` | Eén WCS coverage als GeoTIFF |
