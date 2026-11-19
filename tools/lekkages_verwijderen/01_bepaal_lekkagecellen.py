"""Lekkagecellen bepalen uit een D-Flow FM referentierun.

Een cel die op de eerste tijdstap van de referentierun al nat is, wordt als
lekkage gezien (water dat er zonder doorbraak al staat, bijvoorbeeld langs de
kanalen). Dit script zoekt die cellen op en schrijft de celmiddelpunten weg als
puntenshapefile. Die shapefile is de input voor 02_demp_lekkages_in_zip.py.

Input: FlowFM_map.nc van de referentierun, met
    Mesh2d_face_x, Mesh2d_face_y   celmiddelpunten [m, RD]
    Mesh2d_waterdepth              waterdiepte per tijdstap per cel [m]

Output: puntenshapefile (EPSG:28992) met per natte cel de velden
    cel_idx   celindex in het 2D-grid
    z_nat     waterdiepte op de gekozen tijdstap [m]

Vul hieronder MAP_NC in en draai het script. Standaard wordt eerst een
overzichtskaart getoond; na het sluiten daarvan wordt de shapefile geschreven.
"""

# %%
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

REPO = Path(__file__).resolve().parents[2]

# Instellingen
MAP_NC = None  # bv. r"P:\...\REF2\dflowfm\output\FlowFM_map.nc"
UITVOER_SHP = REPO / "output" / "lekkages" / "Lekkage_locaties_map_t0.shp"

VAR = "Mesh2d_waterdepth"
LABEL = "waterdiepte op t=0 [m]"
TIJDSTAP = 0
MIN_DIEPTE = 0.01  # cellen ondieper dan 1 cm gelden als droog
VELDNAAM = "z_nat"  # attribuutnaam in de shapefile (max 10 tekens)

KAART_TONEN = True
PLOT_STAP = 10  # elke n-de cel plotten; 2 miljoen punten is traag


# %%
def plot_kaart(x, y, z, label, stap=1, extent=None, punten=None, clip=(2, 98)):
    """Scatter map of cell values, colour scale clipped to percentiles."""
    fig, ax = plt.subplots(figsize=(11, 8))
    vmin, vmax = np.nanpercentile(z, clip) if clip else (None, None)
    sc = ax.scatter(
        x[::stap], y[::stap], c=z[::stap], s=0.5,
        cmap="viridis", linewidths=0, vmin=vmin, vmax=vmax,
    )
    fig.colorbar(sc, ax=ax, label=label)
    if punten:
        for px, py in punten:
            ax.plot(px, py, "rx", ms=10, mew=2)
    if extent:  # (xmin, xmax, ymin, ymax)
        ax.set(xlim=extent[:2], ylim=extent[2:])
    ax.set(xlabel="x [m RD]", ylabel="y [m RD]", aspect="equal")
    ax.set_title(label)
    plt.tight_layout()
    plt.show()


def schrijf_shapefile(x, y, z, pad, veld="waarde"):
    """Write cell centres where z is finite and non-zero as RD points."""
    import geopandas as gpd

    mask = np.isfinite(z) & (z != 0)
    gdf = gpd.GeoDataFrame(
        {"cel_idx": np.flatnonzero(mask), veld[:10]: z[mask]},  # dbf: max 10 tekens
        geometry=gpd.points_from_xy(x[mask], y[mask]),
        crs="EPSG:28992",
    )
    gdf.to_file(pad)
    print(f"{len(gdf):,} punten weggeschreven naar {pad}")


def main():
    if MAP_NC is None:
        raise SystemExit("Vul MAP_NC in bovenin het script (pad naar FlowFM_map.nc).")

    ds = xr.open_dataset(MAP_NC)
    print(ds[VAR])

    x = ds["Mesh2d_face_x"].values
    y = ds["Mesh2d_face_y"].values
    diepte = ds[VAR].isel(time=TIJDSTAP).values
    print(f"{VAR}: min={np.nanmin(diepte):.3f}  max={np.nanmax(diepte):.3f}  n={diepte.size}")

    # droge cellen wegmaskeren, anders domineert het droge maaiveld de kaart
    z_nat = np.where(diepte > MIN_DIEPTE, diepte, np.nan)

    if KAART_TONEN:
        plot_kaart(x, y, z_nat, LABEL, stap=PLOT_STAP)

    Path(UITVOER_SHP).parent.mkdir(parents=True, exist_ok=True)
    schrijf_shapefile(x, y, z_nat, UITVOER_SHP, veld=VELDNAAM)


# %%
if __name__ == "__main__":
    main()
