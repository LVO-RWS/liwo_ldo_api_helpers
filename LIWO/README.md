# LIWO Scripts

## Structuur

- `LIWO/`: scripts voor dagelijks gebruik.
- Output staat standaard onder `output/liwo/...`.
- De base URL komt uit `.env` via `LIWO_BASE`.

## Belangrijkste Scripts

- `ontdek_services_liwo.py`
  - Overzicht van workspaces en beschikbare services.
- `export_scenario_ids_per_workspace_liwo.py`
  - Haalt scenario-ID’s per workspace uit de capabilities.
- `download_wfs_laag_liwo.py`
  - Downloadt één WFS-laag als GeoPackage.
- `download_basisinformatie_liwo.py`
  - Downloadt geselecteerde lagen uit `LIWO_Basis`.
- `download_alle_lagen_liwo.py`
  - Bulk-download van WFS en WCS via één script.
  - WMS is view-only en staat bewust niet in dit downloadscript.
- `export_wcs_coverages_liwo.py`
  - Inventariseert beschikbare WCS coverages.

Voor LIWO scenario’s geldt: gebruik bij voorkeur de LDO scripts voor selectie en downloads.
De LIWO scripts zijn vooral bedoeld voor service-ontdekking en basisinformatie.
