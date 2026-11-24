"""Lekkages dempen in alle scenario's van een zip met D-Flow FM-resultaten.

Leest de lekkagecellen uit een shapefile (de punten uit
01_bepaal_lekkagecellen.py, of zelf getekende polygonen) en zet die cellen in
elk scenario droog. De input-zip blijft ongewijzigd; het resultaat komt in een
nieuwe zip met dezelfde mappen en bestandsnamen.

Verwachte opbouw van de input-zip:
    <scenario>/FlowFM_fou.nc   fourier-output, 1 waarde per cel
    <scenario>/FlowFM_clm.nc   classmap-output, klassenummer per tijdstap per cel
Andere bestanden in de zip worden niet meegenomen.

Wat er per gedempte cel verandert:
    FlowFM_fou.nc  Mesh2d_fourier001_max_depth -> 0
                   Mesh2d_fourier001_max       -> bodemhoogte (Mesh2d_flowelem_bl),
                                                  of met WATERSTAND_BRON = "klasse"
                                                  de waterstandsklasse van t=0
    FlowFM_clm.nc  Mesh2d_waterdepth           -> alle tijdstappen klasse 1 (droog)
                   Mesh2d_s1                   -> alle tijdstappen de klasse van t=0
                                                  als die bij de bodem past, anders
                                                  de klasse van de bodemhoogte

Cellen zoeken: een punt raakt de cel met exact hetzelfde middelpunt, dus de
punten moeten ongewijzigd uit 01_bepaal_lekkagecellen.py komen. Er wordt op
coördinaat gekoppeld, niet op cel_idx: de scenario's zijn anders geknipt dan de
referentierun, waardoor de celnummers verschillen. Een polygoon raakt alle
cellen waarvan het middelpunt erbinnen ligt (de rand telt niet mee, eventueel
ruimer met BUFFER). Geometrieën zonder cel worden per scenario gemeld.

Per scenario worden controles geprint: vooraf op de aannames (OK / LET OP /
INFO) en achteraf door het geschreven bestand terug te lezen. Mislukt een
controle achteraf, dan komt het scenario niet in de output-zip.

Scenario's zonder lekkage worden met KOPIEER_ONGEWIJZIGD byte-voor-byte
overgenomen. Een scenario dat al in de output-zip staat wordt overgeslagen
(OVERSLAAN_ALS_KLAAR), zodat je na afbreken kunt doorgaan. Bij een fout of
Ctrl+C wordt een half geschreven scenario uit de output-zip teruggedraaid; bij
een harde onderbreking (stroom weg, proces afgeschoten) kan de zip wel
onleesbaar worden.

Let op: in het clm-bestand staan klassenummers, geen meters. Met
WATERSTAND_BRON = "klasse" is de nieuwe waterstand in het fou-bestand dus niet
nauwkeuriger dan de klassebreedte.

Getest met Python 3.12; het kopieren zonder opnieuw inpakken gebruikt interne
velden van zipfile.
"""

# %%
from contextlib import contextmanager
from pathlib import Path
import shutil
import struct
import tempfile
import time
import zipfile

import geopandas as gpd
import matplotlib.pyplot as plt
import netCDF4
import numpy as np
import shapely
import xarray as xr

# %%
REPO = Path(__file__).resolve().parents[2]

# Instellingen
ZIP_IN = None    # bv. r"C:\...\Resultaten_nc_BK.zip"
ZIP_UIT = None   # None = output/lekkages/<naam van ZIP_IN> in deze repo
SHP = REPO / "output" / "lekkages" / "Lekkage_locaties_map_t0.shp"  # output van 01
TEMP_MAP = None        # None = systeem-temp; liefst een snelle lokale schijf

# None = alle scenario's in de zip; of een lijst
MAPPEN = None               # ["MK_Oost_1", "MK_Oost_2"]
OVERSLAAN_ALS_KLAAR = True    # scenario dat al in de output-zip staat -> overslaan
KOPIEER_ONGEWIJZIGD = True    # True: ook scenario's zonder lekkage in de output-zip
                              # (ruwe kopie, byte-identiek aan de input)
KAART_TONEN = False
ZIP_NIVEAU = 6                # deflate-niveau; 6 = zelfde als de input-zip

CLM_DIEPTE = "Mesh2d_waterdepth"            # klassen [-]
CLM_WATERSTAND = "Mesh2d_s1"                # klassen [-]
FOU_DIEPTE = "Mesh2d_fourier001_max_depth"  # max inundatiediepte [m]
FOU_WATERSTAND = "Mesh2d_fourier001_max"    # max waterstand [m NAP]
BODEM = "Mesh2d_flowelem_bl"                # bodemhoogte [m NAP], terugvaloptie

EPSG = 28992            # RD New; de netcdf-coordinaten staan hierin
BUFFER = 0.0            # polygonen oprekken [m], voor randcellen

WATERSTAND_BRON = "bodem"   # nieuwe fou-max: "bodem" (diepte 0 -> waterstand =
                            # bodemhoogte) of "klasse" (klasse van t=0 uit clm)

KLASSE_WAARDE = "midden"  # alleen bij "klasse": "midden" of "ondergrens"
TOLERANTIE = 1e-3       # [m] marge voor de controles
SCHRIJVEN = True       # veiligheidsknop: pas op True als de kaart klopt

CLM_NAAM = "FlowFM_clm.nc"
FOU_NAAM = "FlowFM_fou.nc"
BUFFERGROOTTE = 16 * 1024 * 1024    # bytes per lees/schrijfslag bij kopieren

# %%
# ------------------------------------------------------------- hulpfuncties
def cellen_per_polygoon(x, y, geoms):
    """Return {geometry number: cell indices} for cell centres inside each geometry.

    Uses `contains`: for polygons, centres exactly on the boundary are not
    included; for points, only a cell centre at exactly the same coordinate.
    Geometries without any cell are left out of the result.
    """
    boom = shapely.STRtree(shapely.points(x, y))
    ivlak, icel = boom.query(geoms, predicate="contains")
    volgorde = np.lexsort((icel, ivlak))
    ivlak, icel = ivlak[volgorde], icel[volgorde]
    grens = np.flatnonzero(np.diff(ivlak)) + 1
    return {int(v[0]): c for v, c in zip(np.split(ivlak, grens),
                                         np.split(icel, grens)) if v.size}



def klassegrenzen(ds, naam):
    """Return lower and upper bound per class as an (nclasses, 2) array.

    Open bounds (e.g. "below_-10m") are stored as the netCDF fill value
    (~9.97e36) and become -inf / +inf.
    """
    g = np.asarray(ds[ds[naam].attrs["flag_bounds"]].values, dtype=float)
    if g.ndim == 1:                          # n+1 drempels i.p.v. n paren
        g = np.column_stack([g[:-1], g[1:]])
    g = g.copy()
    g[:, 0] = np.where(np.abs(g[:, 0]) > 1e30, -np.inf, g[:, 0])
    g[:, 1] = np.where(np.abs(g[:, 1]) > 1e30, np.inf, g[:, 1])
    return g


def klasse_naar_meters(grenzen, klassen, hoe=KLASSE_WAARDE):
    """Convert class numbers (flag_values start at 1) to a value in metres."""
    onder, boven = grenzen[:, 0], grenzen[:, 1]
    boven = np.where(np.isfinite(boven), boven, onder)   # open bovenste klasse
    waarde = onder if hoe == "ondergrens" else 0.5 * (onder + boven)
    waarde = np.where(np.isfinite(waarde), waarde, np.nan)  # open onderste
                                                            # klasse -> bodem

    rij = np.clip(klassen.astype(np.int64) - 1, 0, waarde.size - 1)
    uit = waarde[rij]
    uit[klassen < 1] = np.nan               # 0 / fill = geen klasse
    return uit


def kaart(x, y, diepte, idx, vlakken, titel, png=None, marge=100.0):
    """Plot the affected cells with the leak geometries on top."""
    xmin, xmax = x[idx].min() - marge, x[idx].max() + marge
    ymin, ymax = y[idx].min() - marge, y[idx].max() + marge
    venster = np.flatnonzero((x > xmin) & (x < xmax) & (y > ymin) & (y < ymax))

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.scatter(x[venster], y[venster], s=4, color="#eee", zorder=1)
    sc = ax.scatter(x[idx], y[idx], c=diepte[idx], s=14, cmap="Blues",
                    vmin=0, zorder=3)
    fig.colorbar(sc, ax=ax, label="inundatiediepte [m]")
    vlakken.boundary.plot(ax=ax, color="#c50", lw=1.2, zorder=4)
    ax.set(xlim=(xmin, xmax), ylim=(ymin, ymax), aspect="equal",
           xlabel="x [m RD]", ylabel="y [m RD]",
           title=f"{titel}: {idx.size} cellen worden gedempt")
    plt.tight_layout()
    if png is None:
        plt.show()
    else:
        fig.savefig(png, dpi=150)
        plt.close(fig)


def fou_dempen(pad, indices, waterstand):
    """Set max depth to 0 and max water level to `waterstand`."""
    with netCDF4.Dataset(pad, "r+") as nc:
        nc.variables[FOU_DIEPTE][indices] = 0.0
        nc.variables[FOU_WATERSTAND][indices] = waterstand


def klasse_van(grenzen, waarde):
    """Return the class number (1..n) that `waarde` falls in (lower <= waarde)."""
    k = np.searchsorted(grenzen[:, 0], waarde, side="right")
    return np.clip(k, 1, len(grenzen))


def droge_klassen(bodem, klasse_d0, klasse_w0, grenzen_w):
    """New clm classes for the damped cells: dry, water level at bed level.

    If a cell is dry at the first time step and its bed level lies in that
    step's water level class, that class is kept (frozen at t=0); otherwise
    the class of the bed level is used.
    Returns (depth classes, water level classes, past_t0).
    """
    klasse_d0 = np.asarray(klasse_d0).astype(np.int64)
    klasse_w0 = np.asarray(klasse_w0).astype(np.int64)
    rij = np.clip(klasse_w0 - 1, 0, len(grenzen_w) - 1)
    past_t0 = ((klasse_d0 == 1) & (klasse_w0 >= 1)
               & (bodem >= grenzen_w[rij, 0] - TOLERANTIE)
               & (bodem <= grenzen_w[rij, 1] + TOLERANTIE))
    nieuw_d = np.ones_like(klasse_d0)            # klasse 1 = 0 tot 2 cm
    nieuw_w = np.where(past_t0, klasse_w0, klasse_van(grenzen_w, bodem))
    return nieuw_d, nieuw_w, past_t0


def clm_droogzetten(pad, indices, waarden):
    """Set every time step of the given cells to a fixed class.

    `waarden` is {variable name: class per cell in `indices`}. Data is read,
    changed and written per chunk column (all time x chunk width), so each
    compressed chunk is touched only once; untouched columns are skipped.
    """
    with netCDF4.Dataset(pad, "r+") as nc:
        for naam, nieuw in waarden.items():
            var = nc.variables[naam]
            var.set_auto_mask(False)         # klassenummers, niet maskeren
            nieuw = nieuw.astype(var.dtype)
            kolommen = list(chunk_kolommen(var, indices))
            for j0, j1, lokaal, sel in kolommen:
                blok = var[:, j0:j1]         # nt x breedte, ~1,7 MB bij int8
                blok[:, lokaal] = nieuw[sel]
                var[:, j0:j1] = blok
            print(f"  {naam}: {var.shape[0]} tijdstappen vastgezet "
                  f"({len(kolommen)} chunk-kolommen)")


def chunk_kolommen(var, indices):
    """Yield (j0, j1, local indices, mask on `indices`) per affected chunk column."""
    ncel = var.shape[1]
    chunks = var.chunking()
    breedte = chunks[1] if isinstance(chunks, list) else 20_000
    kolom = indices // breedte
    for k in np.unique(kolom):
        j0, j1 = k * breedte, min((k + 1) * breedte, ncel)
        sel = kolom == k
        yield j0, j1, indices[sel] - j0, sel


# ------------------------------------------------------------- controles
def meld(ok, tekst):
    """Print a check line; return 1 if it is a warning."""
    print(f"  [{'OK' if ok else 'LET OP'}] {tekst}")
    return 0 if ok else 1


def info(ok, tekst):
    """Like `meld`, for deviations that are handled: prints [INFO], not counted."""
    print(f"  [{'OK' if ok else 'INFO'}] {tekst}")
    return 0


def controles_vooraf(diepte, wst, bodem, klasse_d0, klasse_w0,
                     grenzen_d, grenzen_w, wst_nieuw):
    """Check assumptions and new values (arrays already cut to the affected cells).

    Returns the number of warnings.
    """
    print("controles vooraf:")
    n, w = diepte.size, 0

    afw = np.abs(np.clip(wst - bodem, 0, None) - diepte)
    k = int(np.sum(afw > TOLERANTIE))
    w += meld(k == 0, f"origineel fou: max waterstand - bodem = max diepte "
                      f"({k} van {n} cellen wijken af, max {np.nanmax(afw):.3f} m)")

    nat0 = klasse_d0 > 1
    w += info(not nat0.any(),
              f"clm eerste tijdstap droog (diepteklasse 1, < {grenzen_d[0, 1]:.3f} m): "
              f"{int(nat0.sum())} van {n} cellen al nat"
              + (f" (tot klasse {int(klasse_d0.max())}); worden in het clm "
                 f"droog gezet, net als de rest" if nat0.any() else ""))

    rij = np.clip(klasse_w0.astype(np.int64) - 1, 0, len(grenzen_w) - 1)
    buiten = ((bodem < grenzen_w[rij, 0] - TOLERANTIE)
              | (bodem > grenzen_w[rij, 1] + TOLERANTIE) | (klasse_w0 < 1))
    w += info(not buiten.any(),
              f"bodemhoogte valt in de clm-waterstandsklasse van de eerste "
              f"tijdstap: {int(buiten.sum())} van {n} cellen niet"
              + ("; die krijgen de klasse van de bodemhoogte"
                 if buiten.any() else ""))

    leeg = ~np.isfinite(bodem)
    w += meld(not leeg.any(), f"bodemhoogte bekend: {int(leeg.sum())} cellen zonder")

    print(f"  nieuwe max waterstand ({WATERSTAND_BRON}): "
          f"{np.nanmin(wst_nieuw):.3f} tot {np.nanmax(wst_nieuw):.3f} m NAP "
          f"(was {np.nanmin(wst):.3f} tot {np.nanmax(wst):.3f})")
    verschil = wst_nieuw - bodem
    boven = verschil > TOLERANTIE
    onder = verschil < -TOLERANTIE
    hoger = wst_nieuw > wst + TOLERANTIE
    leeg = ~np.isfinite(wst_nieuw)
    w += meld(not boven.any(), f"nieuwe max waterstand niet boven bodem: "
              f"{int(boven.sum())} cellen erboven"
              + (f", tot {np.nanmax(verschil):.3f} m (dan klopt max_depth = 0 niet)"
                 if boven.any() else ""))
    w += meld(not onder.any(), f"nieuwe max waterstand niet onder bodem: "
              f"{int(onder.sum())} cellen eronder"
              + (f", tot {-np.nanmin(verschil):.3f} m" if onder.any() else ""))
    w += meld(not hoger.any(), f"nieuwe max waterstand niet hoger dan de oude: "
              f"{int(hoger.sum())} cellen hoger")
    w += meld(not leeg.any(), f"nieuwe max waterstand overal gevuld: "
              f"{int(leeg.sum())} cellen leeg")
    return w


def controle_fou(pad, indices, wst_nieuw):
    """Read back the written fou file and count deviations."""
    with netCDF4.Dataset(pad) as nc:
        d = np.ma.filled(nc.variables[FOU_DIEPTE][:], np.nan)[indices]
        m = np.ma.filled(nc.variables[FOU_WATERSTAND][:], np.nan)[indices]
    nul = int(np.sum(d == 0))
    w = meld(nul == indices.size, f"fou teruggelezen: max_depth = 0 in {nul} van "
                                  f"{indices.size} cellen")
    goed = int(np.sum(np.isclose(m, wst_nieuw, atol=TOLERANTIE, equal_nan=True)))
    w += meld(goed == indices.size, f"fou teruggelezen: max waterstand zoals "
                                    f"bedoeld in {goed} van {indices.size} cellen")
    return w


def controle_clm(pad, indices, waarden):
    """Read back the written clm file: every time step must hold the new class."""
    w = 0
    with netCDF4.Dataset(pad) as nc:
        for naam, nieuw in waarden.items():
            var = nc.variables[naam]
            var.set_auto_mask(False)
            afwijkend = 0
            for j0, j1, lokaal, sel in chunk_kolommen(var, indices):
                blok = var[:, j0:j1][:, lokaal]
                afwijkend += int(np.any(blok != nieuw[sel], axis=0).sum())
            w += meld(afwijkend == 0, f"clm teruggelezen: {naam} in alle "
                      f"tijdstappen zoals bedoeld in {indices.size - afwijkend} "
                      f"van {indices.size} cellen")
    return w


# ------------------------------------------------------------- zip-functies
def zip_uitpakken(zin, entry, doel):
    """Stream one zip entry to `doel` without extracting the rest."""
    with zin.open(entry) as bron, open(doel, "wb") as uit:
        shutil.copyfileobj(bron, uit, BUFFERGROOTTE)


def _zonder_zip64(extra):
    """Drop Zip64 fields (id 1) from an extra field; zipfile writes its own."""
    uit, p = b"", 0
    while p + 4 <= len(extra):
        veld, n = struct.unpack("<HH", extra[p:p + 4])
        if veld != 1:
            uit += extra[p:p + 4 + n]
        p += 4 + n
    return uit


def _zipinfo_zoals(bron, date_time=None):
    """New ZipInfo with the same name, version and attributes as `bron`."""
    zi = zipfile.ZipInfo(bron.filename, date_time or bron.date_time)
    zi.compress_type = bron.compress_type
    zi.create_system = bron.create_system
    zi.create_version = bron.create_version
    zi.extract_version = bron.extract_version
    zi.external_attr = bron.external_attr
    zi.internal_attr = bron.internal_attr
    zi.comment = bron.comment
    zi.extra = _zonder_zip64(bron.extra)
    return zi


def zip_ruw_kopieren(zin, zout, entry):
    """Copy a compressed entry byte for byte, without recompressing.

    zipfile has no public API for this; it uses the same internal fields
    (start_dir, filelist, NameToInfo) as ZipFile.write.
    """
    if entry.flag_bits & 0x01:
        raise ValueError(f"{entry.filename} is versleuteld")
    zin.fp.seek(entry.header_offset)
    kop = zin.fp.read(30)
    if kop[:4] != b"PK\x03\x04":
        raise zipfile.BadZipFile(f"geen lokale header voor {entry.filename}")
    n, m = struct.unpack("<HH", kop[26:30])
    zin.fp.seek(entry.header_offset + 30 + n + m)

    zi = _zipinfo_zoals(entry)
    zi.CRC, zi.compress_size, zi.file_size = (entry.CRC, entry.compress_size,
                                              entry.file_size)
    zi.flag_bits = entry.flag_bits & ~0x08    # groottes staan nu in de header
    zip64 = max(zi.file_size, zi.compress_size) > zipfile.ZIP64_LIMIT

    zout.fp.seek(zout.start_dir)
    zi.header_offset = zout.fp.tell()
    zout.fp.write(zi.FileHeader(zip64))
    rest = entry.compress_size
    while rest:
        buf = zin.fp.read(min(rest, BUFFERGROOTTE))
        if not buf:
            raise zipfile.BadZipFile(f"{entry.filename} is afgekapt")
        zout.fp.write(buf)
        rest -= len(buf)
    zout.start_dir = zout.fp.tell()
    zout.filelist.append(zi)
    zout.NameToInfo[zi.filename] = zi
    zout._didModify = True


def zip_toevoegen(zout, entry, pad):
    """Compress `pad` into the zip under the name and attributes of `entry`."""
    zi = _zipinfo_zoals(entry, date_time=time.localtime()[:6])
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.file_size = Path(pad).stat().st_size
    for attr in ("compress_level", "_compresslevel"):   # py3.13 / py3.12
        if hasattr(zi, attr):
            setattr(zi, attr, ZIP_NIVEAU)
    with open(pad, "rb") as bron, zout.open(zi, "w") as uit:
        shutil.copyfileobj(bron, uit, BUFFERGROOTTE)


@contextmanager
def output_zip():
    """Open the output zip in append mode; on any error, roll back the
    entries added inside this block so no half scenario is left behind.
    """
    ZIP_UIT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_UIT, "a", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=ZIP_NIVEAU) as zout:
        aantal, begin = len(zout.filelist), zout.start_dir
        try:
            yield zout
        except BaseException:
            del zout.filelist[aantal:]
            zout.NameToInfo = {zi.filename: zi for zi in zout.filelist}
            zout.start_dir = begin           # bij afsluiten wordt de rest
            zout._didModify = True           # afgekapt (truncate)
            raise


def staat_in_output(mapnaam):
    """True if both files of this scenario are already in the output zip."""
    if not ZIP_UIT.exists():
        return False
    with zipfile.ZipFile(ZIP_UIT) as z:
        namen = set(z.namelist())
    return {f"{mapnaam}/{CLM_NAAM}", f"{mapnaam}/{FOU_NAAM}"} <= namen


# ------------------------------------------------------------ per scenario
def verwerk_map(zin, mapnaam, infos, vlakken, geoms, tmp):
    """Damp the leak cells in one scenario.

    `infos` are this scenario's zip entries in input order.
    Returns (number of damped cells, number of warnings).
    """
    entries = {Path(i.filename).name: i for i in infos}
    FOU = tmp / FOU_NAAM
    CLM = tmp / CLM_NAAM

    # 1. fou inladen en cellen zoeken
    zip_uitpakken(zin, entries[FOU_NAAM], FOU)
    with xr.open_dataset(FOU) as ds_fou:
        x = ds_fou["Mesh2d_face_x"].values
        y = ds_fou["Mesh2d_face_y"].values
        diepte = ds_fou[FOU_DIEPTE].values      # max diepte, 1 waarde per cel
        wst = ds_fou[FOU_WATERSTAND].values
        bodem_alle = ds_fou[BODEM].values

    # 2. cellen in de polygonen (alleen polygonen die dit scenario raken)
    per_vlak = cellen_per_polygoon(x, y, geoms)
    for i, idx in per_vlak.items():
        nat = idx[diepte[idx] > 0]
        print(f"polygoon {i:>3}: {idx.size:>6} cellen, {nat.size:>6} nat, "
              f"max diepte {diepte[nat].max() if nat.size else 0:.3f} m")
    n_mis = len(geoms) - len(per_vlak)
    info(n_mis == 0, f"{n_mis} van {len(geoms)} geometrieën zonder cel "
                     f"(buiten het grid van dit scenario?)")

    if not per_vlak:
        print("geen cellen geraakt in dit scenario")
        if SCHRIJVEN and KOPIEER_ONGEWIJZIGD:
            with output_zip() as zout:
                for i in infos:
                    zip_ruw_kopieren(zin, zout, i)
            print("ongewijzigd (byte-identiek) naar de output-zip gekopieerd")
        return 0, 0

    idx_alle = np.unique(np.concatenate(list(per_vlak.values())))
    print(f"totaal {idx_alle.size} cellen, waarvan "
          f"{(diepte[idx_alle] > 0).sum()} nat")

    # 3. clm-toestand op tijdstap 0 en nieuwe max waterstand
    zip_uitpakken(zin, entries[CLM_NAAM], CLM)
    with xr.open_dataset(CLM) as ds_clm:
        if ds_clm.sizes.get("Mesh2d_nFaces", x.size) != x.size:
            raise ValueError("clm en fou hebben niet hetzelfde 2D-grid")
        TIJD = ds_clm[CLM_DIEPTE].dims[0]       # naam van de tijd-as in het clm
        tijden = ds_clm[TIJD].values
        print(f"clm: {ds_clm.sizes[TIJD]} tijdstappen over {x.size} cellen, "
              f"van {tijden[0]} tot {tijden[-1]}")
        klasse_w0 = ds_clm[CLM_WATERSTAND].isel({TIJD: 0}).values[idx_alle]
        klasse_d0 = ds_clm[CLM_DIEPTE].isel({TIJD: 0}).values[idx_alle]
        grenzen_w = klassegrenzen(ds_clm, CLM_WATERSTAND)
        grenzen_d = klassegrenzen(ds_clm, CLM_DIEPTE)
    bodem = bodem_alle[idx_alle].astype(float)

    if WATERSTAND_BRON == "bodem":
        wst_nieuw = bodem.copy()
    elif WATERSTAND_BRON == "klasse":
        wst_nieuw = klasse_naar_meters(grenzen_w, klasse_w0)
        ontbreekt = ~np.isfinite(wst_nieuw)
        if ontbreekt.any():                  # geen (eindige) klasse op t=0
            wst_nieuw[ontbreekt] = bodem[ontbreekt]
            print(f"{ontbreekt.sum()} cellen zonder klasse op t=0 -> bodemhoogte")
        breedte = np.diff(grenzen_w, axis=1)[:, 0]
        breedte = breedte[np.isfinite(breedte)]
        print(f"klassebreedte waterstand: {breedte.min():.3f} tot "
              f"{breedte.max():.3f} m - zo nauwkeurig wordt de waterstand")
    else:
        raise ValueError(f"WATERSTAND_BRON onbekend: {WATERSTAND_BRON!r}")

    waarschuwingen = controles_vooraf(diepte[idx_alle], wst[idx_alle], bodem,
                                      klasse_d0, klasse_w0, grenzen_d,
                                      grenzen_w, wst_nieuw)

    # 4. schrijven (in de tijdelijke kopie, daarna in de output-zip)
    if not SCHRIJVEN:
        print("SCHRIJVEN = False: er is niets aangepast.")
        return idx_alle.size, waarschuwingen

    nieuw_d, nieuw_w, past_t0 = droge_klassen(bodem, klasse_d0, klasse_w0,
                                              grenzen_w)
    clm_waarden = {CLM_DIEPTE: nieuw_d, CLM_WATERSTAND: nieuw_w}
    print(f"clm: {int(past_t0.sum())} cellen zoals op de eerste tijdstap, "
          f"{int((~past_t0).sum())} cellen droog gezet met klasse van de bodem")

    fou_dempen(FOU, idx_alle, wst_nieuw)
    print(f"{idx_alle.size} cellen gedempt in {FOU_NAAM}")
    clm_droogzetten(CLM, idx_alle, clm_waarden)
    print(f"{idx_alle.size} cellen droog gezet in {CLM_NAAM}")

    print("controles achteraf:")
    fout = (controle_fou(FOU, idx_alle, wst_nieuw)
            + controle_clm(CLM, idx_alle, clm_waarden))
    # niet geschreven zoals bedoeld -> scenario niet in de output-zip
    if fout:
        raise RuntimeError(f"{fout} controle(s) achteraf mislukt, "
                           f"scenario niet in de output-zip gezet")

    print(f"inpakken in {ZIP_UIT.name} (niveau {ZIP_NIVEAU})")
    with output_zip() as zout:
        for i in infos:                      # zelfde volgorde als de input
            zip_toevoegen(zout, i, tmp / Path(i.filename).name)
    return idx_alle.size, waarschuwingen


# ------------------------------------------------------------ hoofdloop
def polygonen_laden():
    """Read the leak geometries (points or polygons) in EPSG, with BUFFER applied."""
    vlakken = gpd.read_file(SHP)
    if vlakken.crs is None:
        print(f"let op: shapefile zonder CRS, aangenomen dat het EPSG:{EPSG} is")
    elif vlakken.crs.to_epsg() != EPSG:
        print(f"shapefile herprojecteren van {vlakken.crs.to_epsg()} naar {EPSG}")
        vlakken = vlakken.to_crs(EPSG)
    print(f"{len(vlakken)} geometrieën uit {SHP.name}")
    geoms = vlakken.geometry.values
    if BUFFER:
        geoms = shapely.buffer(geoms, BUFFER)
    return vlakken, geoms


def scenarios_in_zip(z):
    """Return {folder: [entries in zip order]} for <folder>/FlowFM_{clm,fou}.nc."""
    scenarios = {}
    for i in z.infolist():
        if i.is_dir():
            continue
        deel = i.filename.split("/")
        if len(deel) == 2 and deel[1] in (CLM_NAAM, FOU_NAAM):
            scenarios.setdefault(deel[0], []).append(i)
        else:
            print(f"let op: {i.filename} wordt niet meegenomen")
    return scenarios


def paden_controleren():
    """Fill in defaults, convert paths to Path and stop on missing input."""
    global ZIP_IN, ZIP_UIT, SHP
    if ZIP_IN is None:
        raise SystemExit("Vul ZIP_IN in bovenin het script (zip met de scenario's).")
    ZIP_IN = Path(ZIP_IN)
    ZIP_UIT = (Path(ZIP_UIT) if ZIP_UIT is not None
               else REPO / "output" / "lekkages" / ZIP_IN.name)
    SHP = Path(SHP)
    for pad in (ZIP_IN, SHP):
        if not pad.exists():
            raise SystemExit(f"Bestand niet gevonden: {pad}")
    print(f"input:  {ZIP_IN}\noutput: {ZIP_UIT}\nlekkages: {SHP}")


def main():
    paden_controleren()
    if ZIP_UIT.resolve() == ZIP_IN.resolve():
        raise ValueError("ZIP_UIT mag niet gelijk zijn aan ZIP_IN")

    vlakken, geoms = polygonen_laden()

    with zipfile.ZipFile(ZIP_IN) as zin:
        scenarios = scenarios_in_zip(zin)    # mapnaam -> entries, input-volgorde
        compleet = [m for m, e in scenarios.items() if len(e) == 2]
        for m in scenarios.keys() - set(compleet):
            print(f"let op: {m} mist {CLM_NAAM} of {FOU_NAAM}, overgeslagen")

        if MAPPEN is None:
            mappen = compleet
        else:
            mappen = [m for m in MAPPEN if m in compleet]
            for m in set(MAPPEN) - set(mappen):
                print(f"let op: {m} staat niet (compleet) in {ZIP_IN.name}")
        print(f"{len(mappen)} scenario's te verwerken\n")

        resultaat = {}
        start = time.perf_counter()
        for nr, mapnaam in enumerate(mappen, 1):
            print(f"\n[{nr}/{len(mappen)}] {mapnaam}")
            if OVERSLAAN_ALS_KLAAR and SCHRIJVEN and staat_in_output(mapnaam):
                print("staat al in output -> overgeslagen")
                resultaat[mapnaam] = "overgeslagen (staat al in output)"
                continue
            t0 = time.perf_counter()
            try:
                with tempfile.TemporaryDirectory(dir=TEMP_MAP) as tmp:
                    n, w = verwerk_map(zin, mapnaam, scenarios[mapnaam],
                                       vlakken, geoms, Path(tmp))
                resultaat[mapnaam] = (f"{n} cellen" if n else "geen lekkages") \
                    + (f", {w}x LET OP" if w else "")
            except Exception as fout:          # één kapotte map stopt de rest niet
                print(f"FOUT in {mapnaam}: {fout!r}")
                resultaat[mapnaam] = f"FOUT: {fout!r}"
            print(f"klaar in {time.perf_counter() - t0:.0f} s")

    print(f"\nsamenvatting ({(time.perf_counter() - start) / 60:.1f} min)")
    for mapnaam, tekst in resultaat.items():
        print(f"{mapnaam:<20} {tekst}")


# %%
if __name__ == "__main__":
    main()