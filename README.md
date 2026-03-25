# LIWO + LDO API Helpers

Praktische scripts voor collega’s die met de LIWO GeoServer en de LDO API werken.

## 0. Starter Guide (eerste keer op je laptop)

Deze stappen zijn bedoeld voor collega’s die nog geen Git, Python of VS Code gebruiken.

### 0.1 Installeer Git (Windows)

1. Ga naar: `https://git-scm.com/download/win`
2. Installeer Git met de standaardinstellingen.
3. Open daarna `Git CMD` via het startmenu.

### 0.2 Installeer Python

1. Ga naar: `https://www.python.org/downloads/windows/`
2. Installeer een recente Python versie (3.11+ aanbevolen).
3. Vink tijdens installatie aan: `Add Python to PATH`.

### 0.3 Installeer VS Code

1. Ga naar: `https://code.visualstudio.com/download`
2. Installeer VS Code met de standaardinstellingen.

### 0.4 Clone deze repository

1. Bepaal waar je de repo wilt opslaan, bijvoorbeeld `C:\RWS\Git`.
2. Open `Git CMD`.
3. Ga naar die map:

```bash
cd C:\RWS\Git
```

4. Clone de repository:

```bash
git clone <URL-VAN-DEZE-REPOSITORY>
```

5. Ga de map in:

```bash
cd liwo_ldo_api_helpers
```

### 0.5 Open de repo in VS Code

1. Open VS Code.
2. Kies `File` > `Open Folder`.
3. Selecteer de map `liwo_ldo_api_helpers`.

### 0.6 (Optioneel) Git naam en e-mail instellen

Alleen nodig als je zelf commits wilt maken:

```bash
git config --global user.name "JOUW_NAAM"
git config --global user.email "JOUW_EMAIL"
```

## 1. Python omgeving opzetten

Er worden meerdere packages gebruikt (o.a. `geopandas`, `rasterio`, `owslib`, `folium`), dus een vaste omgeving is nodig.

Aanbevolen: gebruik Conda.

1. Installeer Miniconda (indien nog niet aanwezig): `https://docs.conda.io/en/latest/miniconda.html`
2. Open `Anaconda Prompt` (of terminal in VS Code).
3. Ga weer naar de map `liwo_ldo_api_helpers` met `cd`
4. Maak de omgeving:

```bash
conda env create -f environment.yml
```

4. Activeer de omgeving:

```bash
conda activate liwo-ldo-api-helpers
```

## 2. LDO API token verkrijgen en instellen

Belangrijk:
- Deze stap is alleen nodig voor **LDO** scripts.
- Voor **LIWO** scripts is geen `LDO_TOKEN` nodig.
- Zowel LDO als LIWO scripts lezen hun base URL uit `.env` via `LDO_BASE` en `LIWO_BASE`.

### 2.1 Inloggen op LDO

1. Ga naar: `https://www.ldo.overstromingsinformatie.nl/`
2. Log in met je RWS-account.
3. Heb je nog geen toegang via BIJ12? Vraag die eerst aan.

### 2.2 Open de API pagina's

Ga vanaf de homepage naar `API` (beperkte documentatie):
- `https://ldo.overstromingsinformatie.nl/api`

Daar staan twee relevante links:
- Authentication API (voor token ophalen): `https://ldo.overstromingsinformatie.nl/auth/`
- Backend API docs (met beschikbare endpoints, waaronder bulk exports): `https://ldo.overstromingsinformatie.nl/api/v1/docs`

### 2.3 Controleer je tenant (op de Authentication API pagina)

1. Zoek de methode `GET /auth/v1/tenants/`.
2. Klik op `Try it out` en voer de request uit.
3. Controleer aan welke tenant je account gekoppeld is.
4. Voor RWS Waterdienst is dit tenant `22`.

### 2.4 Vraag een API token op

1. Scroll naar `POST /auth/v1/token/` en klap deze open.
2. Klik op `Try it out`.
3. Pas in de request body de tenant aan naar:

```json
{
  "tenant": 22
}
```

4. Klik op de blauwe knop `Execute`.
5. In de Response Body krijg je een token terug.
6. Kopieer het token uit het veld `access` (zonder aanhalingstekens).

Let op:
- Het API token is 1 dag geldig.
- Je moet daarna opnieuw een token ophalen.

### 2.5 Zet token in `.env`

1. Kopieer `.env.template` naar `.env` (als `.env` nog niet bestaat).
2. Zet in `.env` in ieder geval deze variabelen goed:

```env
LDO_BASE=https://www.ldo.overstromingsinformatie.nl/api/v1
LIWO_BASE=https://basisinformatie-overstromingen.nl/geoserver
LDO_TOKEN=eyJhbGciOi...
```

Scripts zoeken automatisch naar `.env` vanaf hun eigen map omhoog richting repo-root.
Zonder geldige `LDO_BASE` en `LIWO_BASE` werken de scripts niet.
Zonder geldig `LDO_TOKEN` werken LDO scripts niet.

## 3. Eerste scripts draaien

Begin met deze twee scripts:

```bash
python LDO/ontdek_api_structuur_ldo.py
python LIWO/ontdek_services_liwo.py
```

Output komt standaard onder:
- `output/ldo/...`
- `output/liwo/...`

De meeste scripts schrijven direct in deze hoofdmappen.
Sommige workflows, zoals `de_crossborder`, maken daaronder per run een eigen map.

Bestandsnamen starten standaard met datum+tijd:
- `YYYYMMDD_HHMMSS_<scriptnaam>_<bestandsnaam>`

## 3.1 LDO analytics quick start

Voor Team Overstromingsrisico’s zijn deze scripts vaak het meest bruikbaar:

```bash
python LDO/export_csv_alle_scenarios_ldo.py
python LDO/maak_samenvatting_scenario_catalogus_ldo.py
python LDO/inventariseer_ldo_velden.py
python LDO/inventariseer_bestanden_over_scenarios_ldo.py
python LDO/vind_liwo_scenarios_in_ldo.py
python LDO/vind_mogelijk_nieuwere_liwo_scenarios_in_ldo.py
```


Om voor een lijst van LDO scenario-IDs een excel met alle velden + alle bestanden te downloaden:

```bash
python LDO/batch_ldo_download_ldo.py
```

Voor LIWO-LDO vergelijkingen zijn vooral deze laatste twee nuttig:
- `vind_liwo_scenarios_in_ldo.py` laat zien welke LIWO scenario's nu direct in LDO terug te vinden zijn.
- `vind_mogelijk_nieuwere_liwo_scenarios_in_ldo.py` zoekt naar mogelijk nieuwere publieke LDO-scenario's binnen dezelfde scenario-familie: binnen 100 meter, met dezelfde `projectnaam`, `gebiedsnaam` en `naam doorbraaklocatie`.

Snelle LDO hulp-scripts:

```bash
python LDO/check_token_validity_ldo.py
python LDO/check_permissions_ldo.py
```

Een oude serie scripts gemaakt om te detecteren welke scenarios het Duitse grondgebied betreden in het overstromingsbeeld:

```bash
python LDO/de_crossborder/01_prepare_gadm_grensdata_crossborder_ldo.py
python LDO/de_crossborder/02_export_scenarios_grensoverschrijdend_ldo.py
python LDO/de_crossborder/04_plot_scenarios_nrw_crossborder_ldo.py
```

`02_export_scenarios_grensoverschrijdend_ldo.py` schrijft een
`scenarios_cross_border_and_de_only.csv` met `CROSS_BORDER` + `DE_ONLY`, plus een
aparte `scenarios_cross_border_only.csv` met alleen de echt
grensoverschrijdende scenarios. `04_plot_scenarios_nrw_crossborder_ldo.py`
visualiseert standaard de `CROSS_BORDER` + `DE_ONLY` selectie voor visuele controle.

LIWO bulk-download:

```bash
python LIWO/download_alle_lagen_liwo.py
```

Dit script downloadt alleen WFS en WCS.
WMS is view-only en staat bewust niet in de downloadflow.

## 4. Structuur van de repository

- `LDO/`: LDO scripts voor dagelijks gebruik.
- `LIWO/`: LIWO scripts voor dagelijks gebruik.
- `output/ldo/`: alle LDO outputbestanden.
- `output/liwo/`: alle LIWO outputbestanden.

## 5. Snelle kwaliteitscheck

Smoke test op alle scripts:

```bash
python tools/run_script_smoke.py --timeout-sec 90
```

Let op:
- `tools/run_script_smoke.py` zet automatisch `LIWO_LDO_SMOKE=1` voor snelle controles van zware scripts.
- Voor volledige bulk-runs (alles downloaden/analyseren) draai je de scripts direct zonder deze smoke-variabele.

## 6. Inventaris

Zie `SCRIPT_INVENTARIS.md` voor het complete overzicht.
