"""
Gebruik deze functies om een kaart te maken van een tiff file (bijvoorbeeld waterdiepte) en op te slaan als png in de output path. 
Als je de bres locatie wilt plotten, voeg dan de'
X_coordinaat en Y_coordinaat toe aan de functie. Voor grote bestanden wordt het aangeraden om de downsample factor te veranderen. 

"""

#------ Vul hier de variabelen in -------
tiff_pad = "naam.tiff" 
X_coordinaat = None # Coordinaten in RD New (kopieer van metadata van het scenario)
y_coordinaat = None # Coordinaten in RD New (kopieer van metadata van het scenario)
output_pad = "naam.png"
downsample_factor = 1 # Verander naar een hoger nummer als het een groot bestand is die je wilt plotten

#---- imports --------
from matplotlib_scalebar.scalebar import ScaleBar
from io import BytesIO
import matplotlib.pyplot as plt
from PIL import Image
import rasterio.plot
import numpy as np
import matplotlib.patches as mpatches
import contextily as ctx
import matplotlib.colors as mcolors
from rasterio.coords import BoundingBox
from rasterio.enums import Resampling
from rasterio.transform import Affine
import os


TARGET_CRS = "epsg:28992"
FINAL_WIDTH_MM = 100
RENDER_SCALE = 2
# BASEMAP_SOURCE = ctx.providers.CartoDB.Positron #Dit is een andere basemap met grijstinten
BASEMAP_SOURCE = ctx.providers.OpenStreetMap.Mapnik
MIN_SCALE = 70000
EXPORT_DPI = 150
BASEMAP_ALPHA    = 0.85
BASEMAP_INTERP   = "bilinear"
PNG8             = True
PALETTE_COLORS   = 256 
COMPRESS_LEVEL   = 9

colors = [
    '#cffefd',  # < 0.5   light cyan
    '#95bef5',  # 0.5–1.0 light blue
    '#298dee',  # 1.0–1.5 medium blue
    '#0000c1',  # 1.5–2.0 dark blue
    '#480178',  # 2.0–5.0 dark purple
    '#6f0249',  # > 5.0   deep magenta/maroon
]

# Bin boundaries
bin_bounds = [0, 0.5, 1.0, 1.5, 2.0, 5.0, 999]

CMAP = mcolors.ListedColormap(colors, name='legend_cmap')
NORM = mcolors.BoundaryNorm(bin_bounds, CMAP.N)


def add_north_arrow(ax, x=0.94, y=0.94, size=0.05):
    """Teken een eenvoudige noordpijl op de kaart.

    Args:
        ax: Matplotlib-as waarop de pijl wordt getekend.
        x: Horizontale positie in axes-fractiecoordinaten.
        y: Verticale positie in axes-fractiecoordinaten.
        size: Lengte van de pijl in axes-fractiecoordinaten.
    """
    ax.annotate(
        '', xy=(x, y), xytext=(x, y - size),
        xycoords='axes fraction', textcoords='axes fraction',
        ha='center', va='center',
        arrowprops=dict(facecolor='black', width=3, headwidth=8, headlength=10)
    )
    ax.text(
        x, y + 0.01, 'N',
        transform=ax.transAxes,
        ha='center', va='bottom',
        fontsize=12, fontweight='bold'
    )


def calculate_map_extent(bounds, min_scale, map_size_inches):
    """Bereken een kaartuitsnede die schaal en aspectratio respecteert.

    Args:
        geometry: GeoSeries/GeoDataFrame met geometrie voor de uitsnede.
        min_scale: Minimale schaal (bijv. 70000 voor 1:70.000).
        map_size_inches: Gewenste kaartafmeting in inches (breedte, hoogte).
        dpi: Render-DPI (aanwezig voor API-compatibiliteit).

    Returns:
        Tuple ``(minx, maxx, miny, maxy)`` voor de kaartgrenzen.
    """
    minx, miny, maxx, maxy = bounds
    center_x = (minx + maxx) / 2
    center_y = (miny + maxy) / 2 # This can make the center of the map more downwards, so that there is more room for the legend at the top.
    data_width = maxx - minx
    data_height = maxy - miny
    data_width *= 1.1
    data_height *= 1.3
    target_aspect = map_size_inches[0] / map_size_inches[1]
    min_width_m = map_size_inches[0] * 0.0254 * min_scale
    min_height_m = map_size_inches[1] * 0.0254 * min_scale
    width = max(data_width, min_width_m)
    height = max(data_height, min_height_m)
    current_aspect = width / height
    if current_aspect < target_aspect:
        width = height * target_aspect
    else:
        height = width / target_aspect
    if width < min_width_m or height < min_height_m:
        scale_factor = max(min_width_m / width, min_height_m / height)
        width *= scale_factor
        height *= scale_factor
    final_minx = center_x - width / 1.9
    final_maxx = center_x + width / 1.9
    final_miny = center_y - height / 2
    final_maxy = center_y + height / 2


    return (final_minx, final_maxx, final_miny, final_maxy)


def maak_raster_final(water_diepte_pad, downsample_factor = 1): 
    """Lees een waterdiepteraster in, downsample en crop het tot geldige data.

    Het raster wordt ingelezen vanuit een GeoTIFF-bestand. Waarden kleiner
    dan of gelijk aan nul worden als ongeldig beschouwd en vervangen door
    ``NaN``. Vervolgens wordt het raster bijgesneden tot de kleinste
    rechthoek die alle geldige data bevat. De bijbehorende affine
    transformatie en geografische begrenzing worden hierop aangepast.

    Args:
        water_diepte_pad (str):
            Pad naar het GeoTIFF-bestand met waterdieptes.
        downsample_factor (int, optional):
            Factor waarmee het raster wordt verkleind voor snellere
            verwerking. Standaard ``1``.
        target_crs (str, optional):
            Doel-CRS. Momenteel alleen aanwezig voor compatibiliteit.
            Standaard ``EPSG:28992``.

    Returns:
        tuple:
            - **max_depth_end** (*numpy.ndarray*): Bijgesneden raster.
            - **out_transform** (*Affine*): Transformatie van het raster.
            - **bounds_new** (*BoundingBox*): Nieuwe rastergrenzen.
    """

    # Open raster en lees de data 
    with rasterio.open(water_diepte_pad) as src:
        bounds = src.bounds
        res = src.res
        max_depth = src.read(
            1,  # lees band 1 → geeft 2D array (rows, cols)
            out_shape=(src.height // downsample_factor, src.width // downsample_factor),
            resampling=Resampling.bilinear
        )

        plot_transform = src.transform * src.transform.scale(
            src.width  / (src.width  // downsample_factor),
            src.height / (src.height // downsample_factor)
        )


    resx = res[0] * downsample_factor
    resy = res[1] * downsample_factor
        
    xmin = bounds.left
    ymin = bounds.bottom
    xmax = bounds.right
    ymax = bounds.top

    max_depth[max_depth <= 0] = np.nan
      
    geldige_data = np.isfinite(max_depth) & (max_depth > 0)
    if np.any(geldige_data):
        # Zoek de uiterste indexen waar True staat
        rijen = np.any(geldige_data, axis=1)
        kolommen = np.any(geldige_data, axis=0)
        
        r_min, r_max = np.where(rijen)[0][[0, -1]]
        k_min, k_max = np.where(kolommen)[0][[0, -1]]

        # Snijd de array bij (r_max en k_max zijn inclusief, dus +1 voor slicing)
        max_depth_end = max_depth[r_min:r_max+1, k_min:k_max+1]
        
        # Pas de breedte en hoogte aan naar de nieuwe matrix-grootte
        height, width = max_depth_end.shape

        # Belangrijk: Bereken de nieuwe geografische xmin en ymax op basis van de verschuiving!
        # k_min verschuift de x-as naar rechts, r_min verschuift de y-as naar beneden
        nieuw_xmin = xmin + (k_min * resx)
        nieuw_ymax = ymax - (r_min * abs(resy))  # Let op de min: y gaat van boven naar beneden
        nieuw_xmax = nieuw_xmin + (width * resx)
        nieuw_ymin = nieuw_ymax - (height * abs(resy))

        # Update de transformatie en bounds
        out_transform = Affine.translation(nieuw_xmin, nieuw_ymax) * Affine.scale(resx, -abs(resy))
        bounds_new = BoundingBox(left=nieuw_xmin, bottom=nieuw_ymin, right=nieuw_xmax, top=nieuw_ymax)
        print(f"Raster gecropt! Grootte raster: {width}x{height} pixels.")
    else:
        print("Waarschuwing: Hele raster bevat geen geldige data.")
        bounds_new = BoundingBox(left=xmin, bottom=ymin, right=xmax, top=ymax)

    return max_depth_end, out_transform, bounds_new

from rasterio.transform import array_bounds

def generate_map(max_depth, out_transform, bounds, X_coordinaat, Y_coordinaat, path): 
    """Genereer een kaartafbeelding van een waterdiepteraster en sla deze op als PNG.

        De functie maakt een kaart met een achtergrondkaart van OpenStreetMap,
        projecteert het waterdiepteraster hieroverheen en voegt optioneel een
        locatiepunt toe. Daarnaast worden een legenda, noordpijl en schaalbalk
        weergegeven. De kaart wordt vervolgens opgeslagen als PNG-bestand.

        Args:
            max_depth (numpy.ndarray):
                Raster met waterdieptes. Ongeldige waarden dienen als ``NaN``
                aanwezig te zijn.
            out_transform (Affine):
                Affine transformatie die het raster koppelt aan geografische
                coördinaten.
            bounds (BoundingBox):
                Begrenzing van het raster in de vorm
                ``(left, bottom, right, top)``.
            X_coordinaat (float):
                X-coördinaat van de bres- of interesse-locatie.
            Y_coordinaat (float):
                Y-coördinaat van de bres- of interesse-locatie.
            path (str):
                Uitvoerpad van het PNG-bestand.

        Returns:
            None
    """

    plt.close('all')
    
    # Bepaal uiteindelijke kaartafmetingen
    target_w_in = FINAL_WIDTH_MM / 25.4
    target_h_in = target_w_in * 0.62

    # Render op hogere resolutie voor een scherper eindresultaat
    fig_w_in = target_w_in * RENDER_SCALE
    fig_h_in = target_h_in * RENDER_SCALE
    fig, ax = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=EXPORT_DPI)

    # Laat de kaart de volledige figuur vullen
    ax.set_position([0.0, 0.0, 1.0, 1.0]) 
    # header_ax = fig.add_axes([0.0, 1.0, 1.0, 0.0])  # header strip on top TODO: dit aanpassen als je een header wilt
    # header_ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")


    # Bepaal de kaartuitsnede op basis van rastergrenzen en minimale schaal
    minx, maxx, miny, maxy = calculate_map_extent(
        bounds, MIN_SCALE, (target_w_in, target_h_in)
    )
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect('equal', adjustable='box')
    ax.set_facecolor('#f0f0f0')

    #Voeg achtergrond to aan de kaart
    try:
        ctx.add_basemap(
            ax,
            crs=TARGET_CRS,
            source=BASEMAP_SOURCE,
            zoom='auto',
            alpha=BASEMAP_ALPHA,
            interpolation=BASEMAP_INTERP,
        )
    except Exception:
        ax.set_facecolor('#fafafa')

    # Maskeer ongeldige of onrealistische dieptes
    masked_depth = np.ma.masked_where(np.isnan(max_depth)| (max_depth > 100), max_depth)

    # Plot waterdiepte raster
    rasterio.plot.show(
        masked_depth[np.newaxis, :, :],
        alpha = 0.8,
        transform=out_transform,
        ax=ax,
        cmap=CMAP,
        norm = NORM, 
        interpolation = "nearest"
    )

    #Plot breslocatie
    ax.scatter(X_coordinaat, Y_coordinaat, color = "red", s = 20, zorder = 5)

    # Maak legenda voor waterdiepteklassen
    labels = ['< 0.5', '0.5–1.0', '1.0–1.5', '1.5–2.0', '2.0–5.0', '> 5.0']
    patches = [mpatches.Patch(color=c, label=l) for c, l in zip(colors, labels)]
    ax.legend(handles=patches, title='Water diepte (m)', loc='lower right')
    
    # Voeg schaalbalk en noordpijl toe
    ax.add_artist(ScaleBar(1, 'm', location='lower left'))
    add_north_arrow(ax)
    
    # Verwijder assen en randen voor een nette kaartweergave
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    # plt.show()   #TODO: als je de kaarten meteen hier wilt zien als je ze genereert, als de code niet werkt hierdoor dan deze uncommenten
    
    # sla afbeeding eerst in geheugenbuffer op
    buf = BytesIO()

    fig.savefig(
        buf,
        format="png",
        dpi=EXPORT_DPI,
        facecolor="white",
        edgecolor="white",
        transparent=False,
        pad_inches=0,  # no extra borders
        # NOTE: no bbox_inches="tight"
    )

    # Sluit figuur om geheugen vrij te maken
    plt.close(fig)

    buf.seek(0)
    
    # Open en sla op als PNG
    im = Image.open(buf).convert("RGB")
    im.save(path, optimize=True, compress_level=COMPRESS_LEVEL)

def plot_tiff(water_diepte_pad, X_coordinaat, Y_coordinaat, output_path, downsample_factor = 1):
    """ Hoofdfunctie die alle functies combineert
    """
    max_depth, out_transform, bounds = maak_raster_final(water_diepte_pad, downsample_factor)
    generate_map(max_depth, out_transform, bounds, X_coordinaat, Y_coordinaat, output_path)
    
    print(f"Kaart succesvol opgeslage in {os.path.join(os.getcwd(), output_path)}")


plot_tiff(tiff_pad, X_coordinaat, y_coordinaat, output_pad, downsample_factor)

