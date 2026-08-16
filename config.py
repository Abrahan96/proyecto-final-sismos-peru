"""
config.py
Configuración central del pipeline de sismos - Perú (arquitectura medallón).
"""

from pathlib import Path

# --------------------------------------------------------------------
# Rutas del proyecto
# --------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
GEO_DIR = BASE_DIR / "geo"
LOG_DIR = BASE_DIR / "logs"

for d in (BRONZE_DIR, SILVER_DIR, GOLD_DIR, GEO_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

BRONZE_PATH = BRONZE_DIR / "sismos_raw.parquet"
SILVER_PATH = SILVER_DIR / "sismos_clean.parquet"
GOLD_PATH = GOLD_DIR / "sismos_features.parquet"

# --------------------------------------------------------------------
# API USGS - FDSN Event Web Service
# Documentación: https://earthquake.usgs.gov/fdsnws/event/1/
# --------------------------------------------------------------------
USGS_BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# Bounding box de Perú (rectángulo que cubre todo el territorio).
# Es una primera pasada "barata" para no traer sismos de medio mundo;
# el recorte fino y exacto lo hace geopandas en silver/geo_enrichment.py
# contra los polígonos reales de GADM.
PERU_BBOX = {
    "minlatitude": -18.5,
    "maxlatitude": -0.03,
    "minlongitude": -81.5,
    "maxlongitude": -68.6,
}

DEFAULT_PARAMS = {
    "format": "geojson",
    "minmagnitude": 4.5,
    "orderby": "time",
    **PERU_BBOX,
}

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5

# Primera corrida (sin bronze histórico): se trae desde este año, cargando
# año por año para no saturar la API ni arriesgar timeouts en una sola
# consulta gigante. Corridas siguientes son incrementales (ver bronze/api_client.py).
ANIO_INICIO_HISTORICO = 2000

# --------------------------------------------------------------------
# GADM - fuente de polígonos administrativos de Perú.
# Se usa automáticamente la capa MÁS PROFUNDA disponible (idealmente
# ADM3 = distrito), que trae en cascada país/departamento/provincia/
# distrito en la misma fila. Ver silver/geo_enrichment.py.
# --------------------------------------------------------------------
GADM_PERU_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_PER.gpkg"
GADM_PERU_PATH = GEO_DIR / "gadm41_PER.gpkg"

# --------------------------------------------------------------------
# Columnas de cada capa
# --------------------------------------------------------------------
COLUMNAS_BRONZE = [
    "id",
    "fecha_hora_utc",
    "magnitud",
    "mag_type",
    "lugar",
    "profundidad_km",
    "latitud",
    "longitud",
    "alerta",
    "tsunami",
    "significancia",
    "estado",
    "url_detalle",
    "fecha_actualizacion_utc",
    "fecha_extraccion",
]

# Umbrales de magnitud (escala Richter genérica)
BINS_MAGNITUD = [0, 4.5, 5.5, 6.5, 7.5, 10]
LABELS_MAGNITUD = ["Leve", "Moderado", "Fuerte", "Muy fuerte", "Extremo"]

# Umbrales de profundidad (km)
BINS_PROFUNDIDAD = [0, 70, 300, 1000]
LABELS_PROFUNDIDAD = ["Superficial", "Intermedio", "Profundo"]
