"""
silver/writer.py
Persiste el DataFrame silver (ya limpio, validado y enriquecido).
Silver se recalcula completo en cada corrida a partir de todo el bronze
(ver notas del proyecto, sección 6), así que simplemente sobrescribe.
"""

from __future__ import annotations

import logging

import pandas as pd

from config import SILVER_PATH

logger = logging.getLogger(__name__)


class SilverWriterError(Exception):
    pass


def guardar_silver(df: pd.DataFrame) -> None:
    try:
        df.to_parquet(SILVER_PATH, index=False, engine="pyarrow")
        logger.info("Silver guardado: %s filas en %s.", len(df), SILVER_PATH)
    except Exception as e:
        logger.exception("Error guardando el parquet silver.")
        raise SilverWriterError(f"Fallo en guardar_silver(): {e}") from e


def leer_silver() -> pd.DataFrame:
    try:
        if not SILVER_PATH.exists():
            logger.info("No existe silver todavía (%s).", SILVER_PATH)
            return pd.DataFrame()
        df = pd.read_parquet(SILVER_PATH)
        logger.info("Silver leído: %s filas.", len(df))
        return df
    except Exception as e:
        logger.exception("Error leyendo el parquet silver.")
        raise SilverWriterError(f"Fallo en leer_silver(): {e}") from e
