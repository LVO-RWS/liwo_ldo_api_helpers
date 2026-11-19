# Lekkages verwijderen uit D-Flow FM-resultaten

In sommige modellen staat bij de start van de berekening al water op plekken
waar dat niet hoort, bijvoorbeeld langs regionale beken. Deze twee scripts zoeken die
lekkagecellen op in een referentierun en zetten ze daarna in alle scenario's
droog, zodat ze niet in de overstromingsbeelden terechtkomen.

## Volgorde

1. `01_bepaal_lekkagecellen.py`
   Leest de `FlowFM_map.nc` van een referentierun (zonder doorbraak) en schrijft
   
   alle cellen die op de eerste tijdstap natter zijn dan `MIN_DIEPTE` (1 cm) weg als
   puntenshapefile. Vul bovenin `MAP_NC` in.
2. `02_demp_lekkages_in_zip.py`
   Leest die shapefile en dempt de lekkagecellen in elk scenario van een zip met
   resultaten. Vul bovenin `ZIP_IN` in; `SHP` staat standaard op de output van stap 1.

Een punt dempt de cel met exact hetzelfde middelpunt. Je kunt in QGIS punten
weghalen, maar verschuif ze niet: dan vinden ze geen cel meer. Er wordt op
coördinaat gekoppeld, niet op `cel_idx`. Punten die in een scenario
geen cel vinden (buiten het grid) worden per scenario gemeld.

In plaats van punten mag de shapefile ook polygonen bevatten: dan worden alle
cellen gedempt waarvan het middelpunt binnen een polygoon ligt.

## Input

**Referentierun** (`FlowFM_map.nc`, stap 1):

| variabele | inhoud |
|---|---|
| `Mesh2d_face_x`, `Mesh2d_face_y` | celmiddelpunten [m, RD] |
| `Mesh2d_waterdepth` | waterdiepte per tijdstap per cel [m] |

**Scenario's** (zip, stap 2), per scenario een map met twee bestanden:

```
Resultaten.zip
├── <scenario_1>/
│   ├── FlowFM_fou.nc
│   └── FlowFM_clm.nc
├── <scenario_2>/
│   └── ...
```

| bestand | variabelen die worden gebruikt |
|---|---|
| `FlowFM_fou.nc` | `Mesh2d_face_x/y`, `Mesh2d_fourier001_max` (max waterstand), `Mesh2d_fourier001_max_depth` (max diepte), `Mesh2d_flowelem_bl` (bodemhoogte) |
| `FlowFM_clm.nc` | `Mesh2d_waterdepth` en `Mesh2d_s1` als klassenummers per tijdstap, met de klassegrenzen in de variabele uit het attribuut `flag_bounds` |

Andere bestanden in de zip worden overgeslagen (met een melding). Mappen waarin
één van de twee bestanden ontbreekt ook.

**Lekkages** (shapefile): punten of polygonen in RD New (EPSG:28992). Een andere
projectie wordt omgezet.

## Output

Een nieuwe zip, standaard `output/lekkages/<naam van de input-zip>`, met dezelfde
mappen en bestandsnamen. De input-zip wordt niet aangepast.

Per gedempte cel:

- fou: max diepte wordt 0, max waterstand wordt de bodemhoogte
- clm: alle tijdstappen diepteklasse 1 (droog) en de waterstandsklasse van de bodem

Scenario's waarin geen lekkagecel ligt worden ongewijzigd gekopieerd. Wordt het
script afgebroken, dan kun je het opnieuw starten: scenario's die al in de
output-zip staan worden overgeslagen.

Per scenario worden controles geprint (`OK`, `LET OP`, `INFO`). `LET OP` betekent
dat een aanname niet klopt en je het resultaat moet nakijken. Faalt een controle
op het geschreven bestand, dan komt dat scenario niet in de output-zip.

## Tips

- Zet bij een eerste run `SCHRIJVEN = False` en `MAPPEN = ["<één scenario>"]`; dan
  zie je de controles zonder dat er iets wordt weggeschreven.
- Zet `TEMP_MAP` op een snelle lokale schijf; per scenario worden de twee
  netCDF-bestanden tijdelijk uitgepakt.
