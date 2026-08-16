"""
silver/schemas.py
Esquemas Pandera para validar los datos en cada frontera de capa.
"""

import pandera.pandas as pa
from pandera.pandas import Column, Check, DataFrameSchema

# --------------------------------------------------------------------
# Esquema de entrada: lo que debe cumplir el bronze antes de limpiar
# --------------------------------------------------------------------
schema_bronze = DataFrameSchema(
    {
        "id": Column(str, nullable=False, unique=True),
        "fecha_hora_utc": Column("datetime64[ns, UTC]", nullable=False),
        "magnitud": Column(float, Check.in_range(-2, 10), nullable=False),
        "mag_type": Column(str, nullable=True),
        "lugar": Column(str, nullable=True),
        "profundidad_km": Column(float, Check.in_range(-5, 800), nullable=True),
        "latitud": Column(float, Check.in_range(-90, 90), nullable=False),
        "longitud": Column(float, Check.in_range(-180, 180), nullable=False),
        "alerta": Column(str, nullable=True),
        "tsunami": Column("Int64", nullable=True),
        "significancia": Column("Int64", nullable=True),
        "estado": Column(str, nullable=True),
        "url_detalle": Column(str, nullable=True),
        "fecha_actualizacion_utc": Column("datetime64[ns, UTC]", nullable=True),
        "fecha_extraccion": Column("datetime64[ns, UTC]", nullable=False),
    },
    coerce=False,   # bronze ya viene tipado desde bronze/writer.py
    strict=False,   # permite columnas extra sin romper
)

# --------------------------------------------------------------------
# Esquema de salida: lo que debe cumplir silver ya limpio y enriquecido
# --------------------------------------------------------------------
schema_silver = DataFrameSchema(
    {
        "id": Column(str, nullable=False, unique=True),
        "fecha_hora_utc": Column("datetime64[ns, UTC]", nullable=False),
        "magnitud": Column(float, Check.in_range(-2, 10), nullable=False),
        "profundidad_km": Column(float, Check.in_range(-5, 800), nullable=False),
        "latitud": Column(float, Check.in_range(-90, 90), nullable=False),
        "longitud": Column(float, Check.in_range(-180, 180), nullable=False),
        "departamento": Column(str, nullable=True),  # nullable=True por seguridad, pero ya casi nunca lo será: sismos en el mar ahora reciben el departamento más cercano (ver geo_enrichment.py)
        "provincia": Column(str, nullable=True),
        "distrito": Column(str, nullable=True),
        "pais": Column(str, nullable=True),
        "tipo_epicentro": Column(str, Check.isin(["Punto fijo", "Mar"]), nullable=False),
        "distancia_costa_km": Column(float, nullable=True),  # solo poblada cuando tipo_epicentro == "Mar"
    },
    coerce=False,
    strict=False,
)


def validar(df, schema: DataFrameSchema, nombre_capa: str):
    """
    Valida df contra schema. Devuelve el DataFrame validado.
    Lanza pandera.errors.SchemaErrors con el detalle de qué filas/columnas
    fallaron si algo no cumple.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        df_validado = schema.validate(df, lazy=True)
        logger.info("Validación Pandera OK para %s: %s filas.", nombre_capa, len(df_validado))
        return df_validado
    except pa.errors.SchemaErrors as e:
        logger.error(
            "Validación Pandera FALLÓ para %s. %s filas con errores:\n%s",
            nombre_capa, len(e.failure_cases), e.failure_cases,
        )
        raise
