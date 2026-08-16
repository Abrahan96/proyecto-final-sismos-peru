"""
silver/geo_enrichment.py
Cruza los epicentros (lat/lon) contra los polígonos administrativos de
Perú (GADM) usando geopandas, para asignar pais/departamento/provincia/
distrito reales de cada sismo (point-in-polygon, no aproximación por bbox).

Se usa la capa MÁS PROFUNDA disponible en el .gpkg (normalmente ADM3 =
distrito). Esa capa trae en cascada los nombres de TODOS los niveles
superiores en la misma fila (COUNTRY, NAME_1 depto, NAME_2 provincia,
NAME_3 distrito), así que un solo sjoin alcanza para los 4 niveles a
la vez - no hace falta cruzar contra cada nivel por separado.
"""

from __future__ import annotations

import logging

import geopandas as gpd
import pandas as pd
import requests

from config import GADM_PERU_PATH, GADM_PERU_URL

logger = logging.getLogger(__name__)

# Mapeo de nivel GADM -> nombre de columna final en nuestro DataFrame
NIVELES_COLUMNAS = {
    "pais": "COUNTRY",
    "departamento": "NAME_1",
    "provincia": "NAME_2",
    "distrito": "NAME_3",
}


class GeoEnrichmentError(Exception):
    pass


def _descargar_gadm_si_falta() -> None:
    """Descarga el .gpkg de GADM Perú si no existe localmente todavía."""
    if GADM_PERU_PATH.exists():
        return

    logger.info("No existe el shapefile GADM local. Descargando desde %s ...", GADM_PERU_URL)
    try:
        resp = requests.get(GADM_PERU_URL, timeout=120)
        resp.raise_for_status()
        GADM_PERU_PATH.write_bytes(resp.content)
        logger.info("GADM Perú descargado y guardado en %s (%s bytes).", GADM_PERU_PATH, len(resp.content))
    except requests.exceptions.RequestException as e:
        logger.exception("No se pudo descargar el shapefile de GADM.")
        raise GeoEnrichmentError(
            f"Fallo descargando GADM desde {GADM_PERU_URL}: {e}. "
            f"Descárgalo manualmente y colócalo en {GADM_PERU_PATH}."
        ) from e


def _detectar_capa_mas_profunda() -> str:
    """
    Detecta automáticamente la capa de mayor nivel administrativo
    disponible en el .gpkg (idealmente ADM3 = distrito). Se elige la
    de nivel más alto disponible porque esa trae en cascada los nombres
    de todos los niveles superiores en la misma fila.
    """
    try:
        import pyogrio
        info_capas = pyogrio.list_layers(str(GADM_PERU_PATH))
        capas = [fila[0] for fila in info_capas]
    except Exception as e:
        logger.exception("No se pudo listar las capas del .gpkg de GADM.")
        raise GeoEnrichmentError(f"Fallo leyendo capas de {GADM_PERU_PATH}: {e}") from e

    logger.info("Capas disponibles en el .gpkg: %s", capas)

    # busca ADM_ADM3 -> ADM_ADM2 -> ADM_ADM1 -> ADM_ADM0, en ese orden de preferencia
    for nivel in (3, 2, 1, 0):
        candidatos = [
            f"ADM_ADM{nivel}",
            f"ADM_ADM_{nivel}",  # naming real visto en el .gpkg de GADM 4.1 (con guion bajo)
            f"gadm41_PER_{nivel}",
            f"level{nivel}",
        ]
        encontrada = next((c for c in candidatos if c in capas), None)
        if encontrada:
            logger.info("Capa elegida (nivel %s, la más profunda disponible): %s", nivel, encontrada)
            return encontrada

    # fallback total: la última capa listada (asumiendo que GADM las ordena de menor a mayor detalle)
    if not capas:
        raise GeoEnrichmentError(f"El .gpkg {GADM_PERU_PATH} no tiene ninguna capa legible.")
    logger.warning("No se encontró naming estándar ADM_ADMx. Usando fallback: %s", capas[-1])
    return capas[-1]


def cargar_gadm_peru() -> gpd.GeoDataFrame:
    """
    Carga (descargando si hace falta) los polígonos de Perú con los 4
    niveles administrativos disponibles: pais, departamento, provincia, distrito.
    Si la capa detectada no trae alguno de esos niveles (ej. solo llega a
    ADM1), esa(s) columna(s) quedan como NaN en vez de romper el pipeline.
    """
    try:
        _descargar_gadm_si_falta()
        capa = _detectar_capa_mas_profunda()

        gdf = gpd.read_file(GADM_PERU_PATH, layer=capa)

        columnas_finales = {}
        for nombre_final, nombre_gadm in NIVELES_COLUMNAS.items():
            if nombre_gadm in gdf.columns:
                columnas_finales[nombre_gadm] = nombre_final
            else:
                logger.warning(
                    "La capa %s no trae la columna %s (nivel '%s'). Esa columna quedará vacía.",
                    capa, nombre_gadm, nombre_final,
                )

        gdf = gdf.rename(columns=columnas_finales)
        columnas_a_mantener = [c for c in NIVELES_COLUMNAS.keys() if c in gdf.columns] + ["geometry"]
        gdf = gdf[columnas_a_mantener]

        # crea con NaN cualquier nivel que no se haya podido detectar, para
        # que el DataFrame de salida tenga siempre las 4 columnas
        for nombre_final in NIVELES_COLUMNAS.keys():
            if nombre_final not in gdf.columns:
                gdf[nombre_final] = pd.NA

        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=4326)
        elif gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        logger.info("GADM Perú cargado: %s polígonos (capa %s).", len(gdf), capa)
        return gdf

    except GeoEnrichmentError:
        raise
    except Exception as e:
        logger.exception("Error inesperado cargando GADM Perú.")
        raise GeoEnrichmentError(f"Fallo en cargar_gadm_peru(): {e}") from e


def enriquecer_geografia(df: pd.DataFrame, gdf_admin: gpd.GeoDataFrame | None = None) -> pd.DataFrame:
    """
    Cruza cada sismo (lat/lon) contra los polígonos administrativos vía
    sjoin (point-in-polygon), asignando pais/departamento/provincia/distrito
    en un solo cruce.

    Para sismos cuyo epicentro cae en el mar (fuera de todo polígono - muy
    común en Perú por la zona de subducción, donde ocurren justamente los
    sismos más grandes, ej. Pisco 2007), en vez de dejarlos sin zona
    asignada, se les asigna el departamento/provincia/distrito MÁS CERCANO
    (sjoin_nearest, distancia al polígono más próximo). Esto es una
    aproximación práctica para que estos sismos no queden invisibles en
    vistas agrupadas por zona - no es una asignación de "el sismo ocurrió
    ahí", es "la zona terrestre más cercana a su epicentro".

    Se agrega la columna 'tipo_epicentro' ('Punto fijo' = matcheó
    directamente un polígono, 'Mar' = se asignó por cercanía) para que
    siempre quede trazable cuál es cuál.
    """
    try:
        if gdf_admin is None:
            gdf_admin = cargar_gadm_peru()

        puntos = gpd.GeoDataFrame(
            df.copy(),
            geometry=gpd.points_from_xy(df["longitud"], df["latitud"]),
            crs="EPSG:4326",
        )

        # --- Paso 1: match exacto (point-in-polygon) ---
        cruzado = gpd.sjoin(puntos, gdf_admin, how="left", predicate="within")
        cruzado = cruzado.drop(columns=["index_right"], errors="ignore")

        cruzado["tipo_epicentro"] = cruzado["departamento"].notna().map(
            {True: "Punto fijo", False: "Mar"}
        )
        cruzado["distancia_costa_km"] = float("nan")

        # --- Paso 2: para los que cayeron en el mar, asignar el más cercano ---
        mask_mar = cruzado["departamento"].isna()
        n_mar = int(mask_mar.sum())

        if n_mar > 0:
            sin_match = cruzado.loc[mask_mar, ["geometry"]]
            sin_match = gpd.GeoDataFrame(sin_match, geometry="geometry", crs=puntos.crs)

            # Reproyectar a un CRS métrico (Web Mercator) para que la distancia
            # salga en metros reales, no en grados. Para el propósito de
            # "cuál es el polígono más cercano" es una aproximación suficiente
            # dado que Perú está en un rango de latitud acotado.
            crs_metrico = "EPSG:3857"
            sin_match_m = sin_match.to_crs(crs_metrico)
            gdf_admin_m = gdf_admin.to_crs(crs_metrico)

            cercano = gpd.sjoin_nearest(
                sin_match_m, gdf_admin_m, how="left", distance_col="distancia_costa_m"
            )
            # sjoin_nearest puede devolver >1 fila por punto si hay empate exacto
            # de distancia (rarísimo con coordenadas reales, pero se blinda igual
            # para nunca duplicar sismos).
            cercano = cercano[~cercano.index.duplicated(keep="first")]

            columnas_geo = ["pais", "departamento", "provincia", "distrito"]
            cruzado.loc[cercano.index, columnas_geo] = cercano[columnas_geo].values
            cruzado.loc[cercano.index, "distancia_costa_km"] = (
                cercano["distancia_costa_m"] / 1000
            ).round(1)

            logger.info(
                "%s sismos con epicentro en el mar - departamento más cercano asignado "
                "(distancia promedio: %.1f km).",
                n_mar, cruzado.loc[mask_mar, "distancia_costa_km"].astype(float).mean(),
            )

        cruzado = cruzado.drop(columns=["geometry"], errors="ignore")
        cruzado = pd.DataFrame(cruzado).reset_index(drop=True)
        logger.info(
            "Enriquecimiento geográfico completo: %s filas (%s en tierra, %s asignadas por cercanía al mar).",
            len(cruzado), len(cruzado) - n_mar, n_mar,
        )
        return cruzado

    except GeoEnrichmentError:
        raise
    except Exception as e:
        logger.exception("Error en el cruce geoespacial (sjoin).")
        raise GeoEnrichmentError(f"Fallo en enriquecer_geografia(): {e}") from e
