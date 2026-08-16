"""
logger_setup.py
Logging a archivo diario + consola para las 3 capas (bronze/silver/gold).
"""

import logging
from datetime import date

from config import LOG_DIR


def configurar_logging(nombre: str = "sismos_peru_etl") -> logging.Logger:
    log_file = LOG_DIR / f"{nombre}_{date.today().isoformat()}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,  # evita handlers duplicados si se llama más de una vez en la misma sesión
    )
    return logging.getLogger(nombre)
