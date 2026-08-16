"""
etl.py
Orquestador del pipeline medallón: Bronze -> Silver -> Gold.

Uso:
    python etl.py                              # 1a corrida: backfill completo 2000->hoy (por año)
                                                # corridas siguientes: incremental (última fecha -> hoy)
    python etl.py --minmag 6.0                 # sobrescribe la magnitud mínima de config.py
    python etl.py --inicio 2010-01-01 --fin 2010-12-31   # rango manual (ej. reintentar un año que falló)

Exit codes:
    0 -> éxito
    1 -> error en bronze (API)
    2 -> error en silver (limpieza/validación/geo)
    3 -> error en gold (features/normalización)
    4 -> error inesperado no controlado
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

import pandas as pd

from logger_setup import configurar_logging
from config import ANIO_INICIO_HISTORICO

from bronze.api_client import obtener_sismos, rango_incremental, USGSApiError
from bronze.writer import geojson_a_dataframe, guardar_bronze, ultima_fecha_cargada, leer_bronze, BronzeWriterError

from silver.schemas import schema_bronze, schema_silver, validar
from silver.cleaning import limpiar, CleaningError
from silver.geo_enrichment import enriquecer_geografia, GeoEnrichmentError
from silver.optimization import optimizar_memoria, OptimizationError
from silver.writer import guardar_silver, SilverWriterError

from gold.feature_engineering import aplicar_feature_engineering, FeatureEngineeringError
from gold.normalization import agregar_zscore_departamento, NormalizationError
from gold.writer import guardar_gold, GoldWriterError

import pandera


def parse_args():
    parser = argparse.ArgumentParser(description="ETL medallón de sismos - Perú")
    parser.add_argument("--minmag", type=float, default=None, help="Magnitud mínima (sobrescribe config.py)")
    parser.add_argument(
        "--inicio", type=str, default=None,
        help="YYYY-MM-DD. Fuerza un rango manual (ej. para rellenar un hueco puntual). Requiere --fin.",
    )
    parser.add_argument(
        "--fin", type=str, default=None,
        help="YYYY-MM-DD. Usado junto con --inicio para un rango manual.",
    )
    return parser.parse_args()


def _cargar_historico_por_anio(logger, anio_inicio: int, minmag: float | None) -> pd.DataFrame:
    """
    Primera corrida (sin bronze todavía): trae todo el histórico desde
    anio_inicio hasta hoy, año por año. Cada año se guarda en bronze
    apenas se descarga (no se espera a tener todos los años en memoria),
    así que si un año falla, los años anteriores ya quedan a salvo en disco
    y no hay que repetir todo el backfill - basta con reintentar ese año
    puntual con --inicio/--fin.
    """
    anio_actual = date.today().year
    df_bronze = leer_bronze()
    anios_fallidos = []

    for anio in range(anio_inicio, anio_actual + 1):
        starttime = f"{anio}-01-01"
        endtime = f"{anio + 1}-01-01" if anio < anio_actual else date.today().isoformat()

        try:
            logger.info("--- Backfill año %s (%s -> %s) ---", anio, starttime, endtime)
            geojson = obtener_sismos(starttime=starttime, endtime=endtime, minmagnitude=minmag)
            df_nuevo = geojson_a_dataframe(geojson)
            df_bronze = guardar_bronze(df_nuevo)
        except Exception as e:
            logger.error("Falló el backfill del año %s: %s. Se continúa con los años siguientes.", anio, e)
            anios_fallidos.append(anio)

    if anios_fallidos:
        logger.warning(
            "Backfill terminado con años fallidos: %s. Puedes reintentarlos con: "
            "python etl.py --inicio YYYY-01-01 --fin YYYY-12-31",
            anios_fallidos,
        )

    return df_bronze


def etapa_bronze(logger, minmag: float | None, inicio_manual: str | None, fin_manual: str | None):
    """
    Devuelve el DataFrame bronze completo y actualizado.

    - Si se pasan --inicio/--fin: consulta exactamente ese rango (rellenar huecos).
    - Si no hay bronze histórico todavía: backfill completo desde ANIO_INICIO_HISTORICO, por año.
    - Si ya hay bronze: incremental, desde la última fecha cargada hasta hoy.
    """
    try:
        logger.info("=== BRONZE: inicio ===")

        if inicio_manual and fin_manual:
            logger.info("Rango manual forzado: %s -> %s", inicio_manual, fin_manual)
            geojson = obtener_sismos(starttime=inicio_manual, endtime=fin_manual, minmagnitude=minmag)
            df_nuevo = geojson_a_dataframe(geojson)
            df_bronze = guardar_bronze(df_nuevo)

        else:
            ultima_fecha = ultima_fecha_cargada()

            if ultima_fecha is None:
                logger.info(
                    "No hay bronze histórico. Iniciando backfill completo desde %s.",
                    ANIO_INICIO_HISTORICO,
                )
                df_bronze = _cargar_historico_por_anio(logger, ANIO_INICIO_HISTORICO, minmag)

            else:
                starttime, endtime = rango_incremental(ultima_fecha)
                logger.info("Rango incremental: %s -> %s", starttime, endtime)
                geojson = obtener_sismos(starttime=starttime, endtime=endtime, minmagnitude=minmag)
                df_nuevo = geojson_a_dataframe(geojson)
                df_bronze = guardar_bronze(df_nuevo)

        logger.info("=== BRONZE: fin OK (%s filas totales) ===", len(df_bronze))
        return df_bronze

    except (USGSApiError, BronzeWriterError) as e:
        logger.error("BRONZE falló: %s", e)
        raise
    except Exception as e:
        logger.exception("BRONZE: error inesperado.")
        raise


def etapa_silver(logger, df_bronze):
    """Limpia, valida y enriquece geográficamente. Devuelve el DataFrame silver."""
    try:
        logger.info("=== SILVER: inicio ===")

        df_bronze_validado = validar(df_bronze, schema_bronze, "bronze")

        df = limpiar(df_bronze_validado)
        df = enriquecer_geografia(df)

        # Se valida ANTES de optimizar memoria: las reglas de negocio (rangos,
        # nulos, unicidad) importan más que el dtype exacto de almacenamiento.
        # El downcasting es solo para reducir tamaño en disco/RAM, no debe
        # ser motivo de rechazo de un registro válido.
        df_silver = validar(df, schema_silver, "silver")
        df_silver = optimizar_memoria(df_silver)
        guardar_silver(df_silver)

        logger.info("=== SILVER: fin OK (%s filas) ===", len(df_silver))
        return df_silver

    except (CleaningError, GeoEnrichmentError, OptimizationError, SilverWriterError) as e:
        logger.error("SILVER falló: %s", e)
        raise
    except pandera.errors.SchemaErrors as e:
        logger.error("SILVER falló validación Pandera: %s filas con error.", len(e.failure_cases))
        raise
    except Exception as e:
        logger.exception("SILVER: error inesperado.")
        raise


def etapa_gold(logger, df_silver):
    """Feature engineering + normalización. Guarda las tablas gold."""
    try:
        logger.info("=== GOLD: inicio ===")

        df_detalle, df_agregaciones = aplicar_feature_engineering(df_silver.copy())
        df_detalle = agregar_zscore_departamento(df_detalle)

        guardar_gold(df_detalle, df_agregaciones)

        logger.info("=== GOLD: fin OK (%s filas detalle) ===", len(df_detalle))
        return df_detalle, df_agregaciones

    except (FeatureEngineeringError, NormalizationError, GoldWriterError) as e:
        logger.error("GOLD falló: %s", e)
        raise
    except Exception as e:
        logger.exception("GOLD: error inesperado.")
        raise


def main() -> int:
    logger = configurar_logging()
    args = parse_args()

    logger.info("########## INICIO ETL sismos_peru_etl ##########")

    try:
        df_bronze = etapa_bronze(logger, args.minmag, args.inicio, args.fin)
    except Exception:
        return 1

    if df_bronze.empty:
        logger.info(
            "Bronze está vacío (sin sismos históricos ni nuevos en este rango). "
            "No hay nada que procesar en silver/gold por ahora. ETL finaliza OK."
        )
        logger.info("########## ETL FINALIZADO OK (sin datos) ##########")
        return 0

    try:
        df_silver = etapa_silver(logger, df_bronze)
    except Exception:
        return 2

    try:
        etapa_gold(logger, df_silver)
    except Exception:
        return 3

    logger.info("########## ETL FINALIZADO OK ##########")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logging.getLogger(__name__).exception("Error inesperado no controlado en main().")
        sys.exit(4)
