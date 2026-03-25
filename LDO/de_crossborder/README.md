# LDO DE Crossborder

Gebruik deze volgorde:

1. `01_prepare_gadm_grensdata_crossborder_ldo.py`
2. `02_export_scenarios_grensoverschrijdend_ldo.py`
3. `03_download_tiffs_grensscenarios_ldo.py`
4. `04_plot_scenarios_nrw_crossborder_ldo.py`

Deze workflow gebruikt:
- `gadm/` voor NL/DE GADM shapefiles
- `output/ldo/de_crossborder/` voor de gegenereerde output

Script `02`, `03` en `04` maken per run een eigen map:
- `YYYYMMDD_HHMMSS_<scriptnaam>/`

Standaard gedrag:
- `02` schrijft Excel + CSV-bestanden naar zijn eigen run-map
- `03` leest standaard de nieuwste output van `02` en schrijft TIFFs naar zijn eigen run-map
- `04` leest standaard de nieuwste output van `02` en schrijft kaart + counts naar zijn eigen run-map
