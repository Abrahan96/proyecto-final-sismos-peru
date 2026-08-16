"""
silver/cleaning.py
Limpieza pandas: nulos, duplicados, tipos. Deja el DataFrame listo
para pasar por geo_enrichment y luego por la validación Pandera de salida.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


class CleaningError(Exception):
    pass


def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Reglas de limpieza:
    - Descarta filas sin id, sin fecha, sin magnitud o sin coordenadas
      (son campos obligatorios para cualquier análisis posterior).
    - Descarta duplicados por id (ya debería venir deduplicado desde bronze,
      esto es una segunda red de seguridad).
    - Rellena profundidad_km nula con 0 si magnitud es válida (evento
      reportado sin profundidad, no lo descartamos, solo lo dejamos en
      superficie por defecto y queda trazable).
    - Tipos numéricos garantizados como float donde corresponde.
    """
    try:
        antes = len(df)

        obligatorias = ["id", "fecha_hora_utc", "magnitud", "latitud", "longitud"]
        df = df.dropna(subset=obligatorias)
        descartadas_nulos = antes - len(df)
        if descartadas_nulos > 0:
            logger.warning("Se descartaron %s filas por nulos en campos obligatorios.", descartadas_nulos)

        antes_dup = len(df)
        df = df.drop_duplicates(subset="id", keep="last")
        descartadas_dup = antes_dup - len(df)
        if descartadas_dup > 0:
            logger.warning("Se descartaron %s filas duplicadas por id (segunda red de seguridad).", descartadas_dup)

        df["profundidad_km"] = df["profundidad_km"].fillna(0.0)

        for col in ["magnitud", "profundidad_km", "latitud", "longitud"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # si la coerción anterior generó algún NaN nuevo, lo descartamos también
        antes_coerce = len(df)
        df = df.dropna(subset=["magnitud", "profundidad_km", "latitud", "longitud"])
        descartadas_coerce = antes_coerce - len(df)
        if descartadas_coerce > 0:
            logger.warning("Se descartaron %s filas con valores no numéricos tras coerción.", descartadas_coerce)

        df = df.reset_index(drop=True)
        logger.info("Limpieza completa: %s filas de entrada -> %s filas limpias.", antes, len(df))
        return df

    except Exception as e:
        logger.exception("Error en la limpieza de datos (silver/cleaning.py).")
        raise CleaningError(f"Fallo en limpiar(): {e}") from e
