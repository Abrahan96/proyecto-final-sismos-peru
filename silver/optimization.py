"""
silver/optimization.py
Optimización de memoria: downcasting de numéricos y tipo category
para strings de baja cardinalidad. Todo vectorizado (sin loops fila a fila).
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


class OptimizationError(Exception):
    pass


def optimizar_memoria(df: pd.DataFrame) -> pd.DataFrame:
    """
    - Downcast de columnas float (float64 -> float32) y enteras
      (int64 -> el int más pequeño que las contenga).
    - Convierte a 'category' las columnas de texto con baja cardinalidad
      (departamento, mag_type, estado, alerta) - vectorizado vía pandas,
      sin iterar filas.
    """
    try:
        antes_mb = df.memory_usage(deep=True).sum() / 1024**2

        columnas_float = ["magnitud", "profundidad_km", "latitud", "longitud"]
        for col in columnas_float:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], downcast="float")

        columnas_int = ["tsunami", "significancia"]
        for col in columnas_int:
            if col in df.columns:
                # Int64 (nullable) no soporta downcast directo; se pasa por
                # float temporalmente solo para el cálculo de downcast, sin
                # perder los nulos reales.
                no_nulos = df[col].notna()
                if no_nulos.any():
                    df.loc[no_nulos, col] = pd.to_numeric(
                        df.loc[no_nulos, col], downcast="integer"
                    )

        columnas_categoria = ["departamento", "provincia", "distrito", "pais", "mag_type", "estado", "alerta", "tipo_epicentro"]
        for col in columnas_categoria:
            if col in df.columns:
                df[col] = df[col].astype("category")

        despues_mb = df.memory_usage(deep=True).sum() / 1024**2
        reduccion_pct = (1 - despues_mb / antes_mb) * 100 if antes_mb > 0 else 0

        logger.info(
            "Optimización de memoria: %.2f MB -> %.2f MB (%.1f%% de reducción).",
            antes_mb, despues_mb, reduccion_pct,
        )
        return df

    except Exception as e:
        logger.exception("Error optimizando memoria del DataFrame.")
        raise OptimizationError(f"Fallo en optimizar_memoria(): {e}") from e
