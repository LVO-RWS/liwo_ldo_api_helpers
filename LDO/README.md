# LDO Scripts

## Structuur

- `LDO/`: scripts voor dagelijks gebruik.
- Output staat standaard onder `output/ldo/...`.
- De base URL komt uit `.env` via `LDO_BASE`.

## Belangrijkste Scripts

- `check_token_validity_ldo.py`
  - Controleert of `LDO_TOKEN` uit `.env` nog geldig is.
- `check_permissions_ldo.py`
  - Controleert snel of je toegang hebt tot een scenario en bestand.
- `ontdek_api_structuur_ldo.py`
  - Schrijft een overzicht van endpoints weg op basis van de OpenAPI.
- `download_excel_alle_scenarios_ldo.py`
  - Downloadt de officiële scenario-export als Excel.
- `inventariseer_ldo_velden.py`
  - Laat van één scenario alle beschikbare veldpaden zien.
- `batch_ldo_download_ldo.py`
  - Downloadt een vaste lijst scenario’s inclusief bestanden en maakt één Excel-overzicht.
- `vind_liwo_scenarios_in_ldo.py`
  - Koppelt LIWO scenario’s aan LDO-ID’s.
- `vind_mogelijk_nieuwere_liwo_scenarios_in_ldo.py`
  - Zoekt naar mogelijk nieuwere publieke LDO-varianten van LIWO-scenario’s.
- `de_crossborder/02_export_scenarios_grensoverschrijdend_ldo.py`
  - Selecteert NL/NRW-relevante scenario’s en schrijft `scenarios_cross_border_and_de_only.csv` (`CROSS_BORDER` + `DE_ONLY`) plus een aparte `scenarios_cross_border_only.csv`.
- `de_crossborder/04_plot_scenarios_nrw_crossborder_ldo.py`
  - Zet de `CROSS_BORDER` + `DE_ONLY` selectie op een kaart voor visuele controle.
