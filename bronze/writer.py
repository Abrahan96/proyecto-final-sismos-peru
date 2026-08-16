"""
bronze/writer.py
Convierte el GeoJSON crudo a DataFrame (aplanado, sin limpiar tipos a fondo -
eso es trabajo de silver) y maneja la persistencia incremental del bronze.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import pandas as pd

from config import BRONZE_PATH, COLUMNAS_BRONZE

logger = logging.getLogger(__name__)


class BronzeWriterError(Exception):
    pass


def _dataframe_bronze_vacio() -> pd.DataFrame:
    """
    DataFrame vacío pero con los DTYPES correctos (no 'object' genérico).
    Necesario porque un pd.DataFrame(columns=...) sin datos no infiere tipos,
    y eso hace fallar la validación Pandera aunque el DataFrame esté vacío
    legítimamente (ej. primera corrida sin bronze aún, o 0 sismos en el rango).
    """
    df = pd.DataFrame(columns=COLUMNAS_BRONZE)
    df["id"] = df["id"].astype(str)
    df["fecha_hora_utc"] = pd.to_datetime(df["fecha_hora_utc"], utc=True).astype("datetime64[ns, UTC]")
    df["magnitud"] = df["magnitud"].astype(float)
    df["mag_type"] = df["mag_type"].astype(str)
    df["lugar"] = df["lugar"].astype(str)
    df["profundidad_km"] = df["profundidad_km"].astype(float)
    df["latitud"] = df["latitud"].astype(float)
    df["longitud"] = df["longitud"].astype(float)
    df["alerta"] = df["alerta"].astype(str)
    df["tsunami"] = df["tsunami"].astype("Int64")
    df["significancia"] = df["significancia"].astype("Int64")
    df["estado"] = df["estado"].astype(str)
    df["url_detalle"] = df["url_detalle"].astype(str)
    df["fecha_actualizacion_utc"] = pd.to_datetime(df["fecha_actualizacion_utc"], utc=True).astype("datetime64[ns, UTC]")
    df["fecha_extraccion"] = pd.to_datetime(df["fecha_extraccion"], utc=True).astype("datetime64[ns, UTC]")
    return df


def geojson_a_dataframe(geojson: dict) -> pd.DataFrame:
    """Aplana el GeoJSON de USGS a un DataFrame bronze (mínimamente tipado)."""
    try:
        features = geojson.get("features", [])
        if not features:
            logger.info("La respuesta de USGS no trae features (0 sismos en el rango).")
            return _dataframe_bronze_vacio()

        filas = []
        ahora_utc = datetime.now(timezone.utc)

        for feat in features:
            props = feat.get("properties", {}) or {}
            geom = feat.get("geometry", {}) or {}
            coords = (geom.get("coordinates") or [None, None, None])
            coords = (coords + [None, None, None])[:3]
            lon, lat, prof = coords

            filas.append({
                "id": feat.get("id"),
                "fecha_hora_utc": pd.to_datetime(props.get("time"), unit="ms", utc=True) if props.get("time") else None,
                "magnitud": props.get("mag"),
                "mag_type": props.get("magType"),
                "lugar": props.get("place"),
                "profundidad_km": prof,
                "latitud": lat,
                "longitud": lon,
                "alerta": props.get("alert"),
                "tsunami": props.get("tsunami"),
                "significancia": props.get("sig"),
                "estado": props.get("status"),
                "url_detalle": props.get("url"),
                "fecha_actualizacion_utc": pd.to_datetime(props.get("updated"), unit="ms", utc=True) if props.get("updated") else None,
                "fecha_extraccion": ahora_utc,
            })

        df = pd.DataFrame(filas)[COLUMNAS_BRONZE]

        # Casteo explícito de tipos - pandas no siempre infiere bien el dtype
        # al construir un DataFrame desde una lista de dicts con valores None mezclados.
        df["fecha_hora_utc"] = pd.to_datetime(df["fecha_hora_utc"], utc=True).astype("datetime64[ns, UTC]")
        df["fecha_actualizacion_utc"] = pd.to_datetime(df["fecha_actualizacion_utc"], utc=True).astype("datetime64[ns, UTC]")
        df["fecha_extraccion"] = pd.to_datetime(df["fecha_extraccion"], utc=True).astype("datetime64[ns, UTC]")
        df["magnitud"] = pd.to_numeric(df["magnitud"], errors="coerce")
        df["profundidad_km"] = pd.to_numeric(df["profundidad_km"], errors="coerce").astype(float)
        df["latitud"] = pd.to_numeric(df["latitud"], errors="coerce")
        df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")
        df["tsunami"] = pd.to_numeric(df["tsunami"], errors="coerce").astype("Int64")
        df["significancia"] = pd.to_numeric(df["significancia"], errors="coerce").astype("Int64")
        df["id"] = df["id"].astype(str)

        logger.info("GeoJSON aplanado a DataFrame bronze: %s filas.", len(df))
        return df

    except Exception as e:
        logger.exception("Error al aplanar el GeoJSON de USGS.")
        raise BronzeWriterError(f"Fallo transformando geojson a DataFrame: {e}") from e


def leer_bronze() -> pd.DataFrame:
    """Lee el parquet bronze existente. Si no existe, devuelve DataFrame vacío."""
    try:
        if not BRONZE_PATH.exists():
            logger.info("No existe bronze todavía (%s). Se creará en esta corrida.", BRONZE_PATH)
            return _dataframe_bronze_vacio()

        df = pd.read_parquet(BRONZE_PATH)
        for col in ["fecha_hora_utc", "fecha_actualizacion_utc", "fecha_extraccion"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], utc=True).astype("datetime64[ns, UTC]")
        logger.info("Bronze leído: %s filas.", len(df))
        return df

    except Exception as e:
        logger.exception("Error leyendo el parquet bronze.")
        raise BronzeWriterError(f"No se pudo leer bronze: {e}") from e


def ultima_fecha_cargada() -> date | None:
    """
    Devuelve la fecha (solo día) del sismo más reciente en bronze,
    usada para calcular el rango incremental de la próxima consulta.
    """
    try:
        df = leer_bronze()
        if df.empty or df["fecha_hora_utc"].isna().all():
            return None
        return df["fecha_hora_utc"].max().date()
    except Exception as e:
        logger.exception("Error calculando última fecha cargada en bronze.")
        raise BronzeWriterError(f"No se pudo determinar última fecha cargada: {e}") from e


def guardar_bronze(df_nuevo: pd.DataFrame) -> pd.DataFrame:
    """
    Combina el DataFrame nuevo con el bronze existente, deduplica por id
    (quedándose con el registro más actualizado) y sobrescribe el parquet.
    """
    try:
        if df_nuevo.empty:
            logger.info("No hay filas nuevas para bronze en esta corrida.")
            return leer_bronze()

        historico = leer_bronze()

        if historico.empty:
            combinado = df_nuevo.copy()
        else:
            combinado = pd.concat([historico, df_nuevo], ignore_index=True)

        antes = len(combinado)
        combinado = combinado.sort_values("fecha_actualizacion_utc")
        combinado = combinado.drop_duplicates(subset="id", keep="last")
        despues = len(combinado)

        combinado = combinado.sort_values("fecha_hora_utc").reset_index(drop=True)
        combinado.to_parquet(BRONZE_PATH, index=False, engine="pyarrow")

        logger.info(
            "Bronze actualizado -> %s filas totales (%s duplicados descartados). Guardado en %s",
            despues, antes - despues, BRONZE_PATH,
        )
        return combinado

    except Exception as e:
        logger.exception("Error guardando el parquet bronze.")
        raise BronzeWriterError(f"No se pudo guardar bronze: {e}") from e
