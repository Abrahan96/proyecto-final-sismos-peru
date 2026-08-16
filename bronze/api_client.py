"""
bronze/api_client.py
Habla con la API de USGS, acotado al bounding box de Perú.
No transforma nada: solo consulta y devuelve GeoJSON crudo o lanza excepción.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import requests

from config import (
    USGS_BASE_URL,
    DEFAULT_PARAMS,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    RETRY_BACKOFF_SECONDS,
)

logger = logging.getLogger(__name__)


class USGSApiError(Exception):
    """Error específico al consultar la API de USGS."""
    pass


def rango_incremental(ultima_fecha: date | None, dias_atras_default: int = 1) -> tuple[str, str]:
    """
    Calcula el rango [starttime, endtime] para la carga incremental.

    - Si hay una última fecha registrada en bronze, arranca desde ahí
      (rellena huecos si el job no corrió uno o varios días).
    - Si no hay historial (primera corrida), usa dias_atras_default.
    """
    hoy = date.today()

    if ultima_fecha is not None:
        # min() por seguridad: si por algún motivo ultima_fecha quedara en el
        # futuro (no debería pasar con data real de USGS, pero sí es posible
        # con relojes desincronizados o datos de prueba), evita un rango
        # inválido (inicio > fin) en la consulta a la API.
        inicio = min(ultima_fecha, hoy)
    else:
        inicio = hoy - timedelta(days=dias_atras_default)

    return inicio.isoformat(), hoy.isoformat()


def obtener_sismos(starttime: str, endtime: str, minmagnitude: float | None = None) -> dict:
    """
    Consulta la API de USGS para el rango dado, acotado al bbox de Perú
    (definido en config.DEFAULT_PARAMS). Reintenta ante fallos de red.
    """
    params = dict(DEFAULT_PARAMS)
    params["starttime"] = starttime
    params["endtime"] = endtime
    if minmagnitude is not None:
        params["minmagnitude"] = minmagnitude

    ultimo_error = None
    for intento in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                "Consultando USGS (intento %s/%s) | rango %s -> %s | bbox Perú | minmag=%s",
                intento, MAX_RETRIES, starttime, endtime, params["minmagnitude"],
            )
            resp = requests.get(USGS_BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            total = data.get("metadata", {}).get("count", len(data.get("features", [])))
            logger.info("Respuesta OK de USGS. Sismos recibidos: %s", total)
            return data

        except requests.exceptions.RequestException as e:
            ultimo_error = e
            logger.warning("Fallo intento %s/%s al consultar USGS: %s", intento, MAX_RETRIES, e)
            if intento < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS)
        except ValueError as e:
            # json.JSONDecodeError hereda de ValueError - respuesta no era JSON válido
            ultimo_error = e
            logger.warning("Respuesta de USGS no es JSON válido (intento %s/%s): %s", intento, MAX_RETRIES, e)
            if intento < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS)

    raise USGSApiError(f"No se pudo obtener datos de USGS tras {MAX_RETRIES} intentos: {ultimo_error}")
