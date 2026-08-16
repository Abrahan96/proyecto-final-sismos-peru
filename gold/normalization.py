"""
gold/normalization.py
Z-score de magnitud, agrupado POR DEPARTAMENTO (no global) - ver notas
del proyecto sección 3: la magnitud es una escala absoluta y comparar
contra el promedio de todo Perú rompería la comparabilidad entre
departamentos. Este z-score responde a "qué tan inusual es este sismo
para el historial propio de su departamento".
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


class NormalizationError(Exception):
    pass


def agregar_zscore_departamento(df: pd.DataFrame) -> pd.DataFrame:
    try:
        def _zscore(x: pd.Series) -> pd.Series:
            std = x.std()
            if std == 0 or pd.isna(std):
                return pd.Series(0.0, index=x.index)
            return (x - x.mean()) / std

        df["magnitud_zscore_departamento"] = (
            df.groupby("departamento", observed=True)["magnitud"].transform(_zscore)
        )

        logger.info("Z-score por departamento calculado sobre %s filas.", len(df))
        return df

    except Exception as e:
        logger.exception("Error calculando z-score por departamento.")
        raise NormalizationError(f"Fallo en agregar_zscore_departamento(): {e}") from e
