"""
gold/writer.py
Persiste las tablas gold: detalle (features) y agregaciones.
"""

from __future__ import annotations

import logging

import pandas as pd

from config import GOLD_PATH, GOLD_DIR

logger = logging.getLogger(__name__)

GOLD_AGREGACIONES_PATH = GOLD_DIR / "sismos_agregaciones_departamento_anio.parquet"


class GoldWriterError(Exception):
    pass


def guardar_gold(df_detalle: pd.DataFrame, df_agregaciones: pd.DataFrame) -> None:
    try:
        df_detalle.to_parquet(GOLD_PATH, index=False, engine="pyarrow")
        df_agregaciones.to_parquet(GOLD_AGREGACIONES_PATH, index=False, engine="pyarrow")
        logger.info(
            "Gold guardado: %s filas detalle en %s | %s filas agregadas en %s.",
            len(df_detalle), GOLD_PATH, len(df_agregaciones), GOLD_AGREGACIONES_PATH,
        )
    except Exception as e:
        logger.exception("Error guardando los parquet de gold.")
        raise GoldWriterError(f"Fallo en guardar_gold(): {e}") from e
