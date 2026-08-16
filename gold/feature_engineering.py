"""
gold/feature_engineering.py
Variables derivadas, agregaciones y binning sobre el silver limpio.
"""

from __future__ import annotations

import logging

import pandas as pd

from config import BINS_MAGNITUD, LABELS_MAGNITUD, BINS_PROFUNDIDAD, LABELS_PROFUNDIDAD

logger = logging.getLogger(__name__)


class FeatureEngineeringError(Exception):
    pass


def agregar_features_temporales(df: pd.DataFrame) -> pd.DataFrame:
    """anio, mes, hora - derivadas de fecha_hora_utc (vectorizado)."""
    try:
        df["anio"] = df["fecha_hora_utc"].dt.year
        df["mes"] = df["fecha_hora_utc"].dt.month
        df["hora"] = df["fecha_hora_utc"].dt.hour
        return df
    except Exception as e:
        logger.exception("Error agregando features temporales.")
        raise FeatureEngineeringError(f"Fallo en agregar_features_temporales(): {e}") from e


def agregar_binning(df: pd.DataFrame) -> pd.DataFrame:
    """magnitud_categoria y profundidad_categoria (escala Richter genérica)."""
    try:
        df["magnitud_categoria"] = pd.cut(
            df["magnitud"], bins=BINS_MAGNITUD, labels=LABELS_MAGNITUD, right=True
        )
        df["profundidad_categoria"] = pd.cut(
            df["profundidad_km"], bins=BINS_PROFUNDIDAD, labels=LABELS_PROFUNDIDAD, right=True
        )
        return df
    except Exception as e:
        logger.exception("Error en el binning de magnitud/profundidad.")
        raise FeatureEngineeringError(f"Fallo en agregar_binning(): {e}") from e


def agregar_recurrencia(df: pd.DataFrame) -> pd.DataFrame:
    """
    dias_desde_ultimo_sismo_mismo_departamento: cuántos días pasaron desde
    el sismo anterior en el MISMO departamento (vectorizado con groupby + diff).
    """
    try:
        df = df.sort_values(["departamento", "fecha_hora_utc"])
        df["dias_desde_ultimo_sismo_mismo_departamento"] = (
            df.groupby("departamento", observed=True)["fecha_hora_utc"]
            .diff()
            .dt.days
        )
        df = df.reset_index(drop=True)
        return df
    except Exception as e:
        logger.exception("Error calculando recurrencia por departamento.")
        raise FeatureEngineeringError(f"Fallo en agregar_recurrencia(): {e}") from e


def construir_agregaciones(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tabla auxiliar: conteo y magnitud promedio por departamento-año.
    Se agrega como tabla separada (no se pega al detalle) porque es
    una granularidad distinta; se puede unir por (departamento, anio)
    cuando se necesite en Streamlit.
    """
    try:
        agg = (
            df.groupby(["pais", "departamento", "anio"], observed=True)
            .agg(
                sismos_total=("id", "count"),
                magnitud_promedio=("magnitud", "mean"),
                magnitud_maxima=("magnitud", "max"),
            )
            .reset_index()
        )
        return agg
    except Exception as e:
        logger.exception("Error construyendo agregaciones por departamento-año.")
        raise FeatureEngineeringError(f"Fallo en construir_agregaciones(): {e}") from e


def aplicar_feature_engineering(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Orquesta todas las transformaciones de esta capa. Devuelve (detalle, agregaciones)."""
    df = agregar_features_temporales(df)
    df = agregar_binning(df)
    df = agregar_recurrencia(df)
    agregaciones = construir_agregaciones(df)
    logger.info("Feature engineering completo: %s filas detalle, %s filas agregadas.", len(df), len(agregaciones))
    return df, agregaciones
