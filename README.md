# sismos_peru_etl

Pipeline de arquitectura medallón (Bronze → Silver → Gold) para sismos en
Perú (magnitud ≥ 4.5), usando la API de USGS, geopandas + GADM para
asignar departamento real por punto-en-polígono, Pandera para validación
automatizada, y features analíticas orientadas a: evolución temporal por
departamento, correlación magnitud/frecuencia, ranking de departamentos
por magnitud, y antecedentes por zona (útil como insumo para consideraciones
de materiales de construcción).

## Estructura

```
sismos_peru_etl/
├── config.py                # rutas, bbox Perú, parámetros API, bins de magnitud/profundidad
├── logger_setup.py          # logging diario a archivo + consola
├── etl.py                   # orquestador: bronze -> silver -> gold
│
├── bronze/
│   ├── api_client.py        # consulta USGS acotada a Perú (bbox), rango incremental
│   └── writer.py             # geojson -> DataFrame, guardado con dedup por id
│
├── silver/
│   ├── schemas.py            # esquemas Pandera (bronze y silver)
│   ├── cleaning.py           # limpieza: nulos, duplicados, tipos
│   ├── geo_enrichment.py     # geopandas + GADM: asigna departamento (sjoin)
│   ├── optimization.py       # downcasting + category (vectorizado)
│   └── writer.py
│
├── gold/
│   ├── feature_engineering.py  # anio/mes/hora, binning Richter, recurrencia, agregaciones
│   ├── normalization.py         # z-score de magnitud AGRUPADO POR DEPARTAMENTO
│   └── writer.py
│
├── data/{bronze,silver,gold}/
├── geo/                       # cache local del .gpkg de GADM (se descarga solo)
├── logs/
├── requirements.txt
├── run_daily.bat
└── .gitignore
```

## Instalación

**Versión requerida y probada: Python 3.14 (64 bits).**

### macOS / Linux

```bash
cd sismos_peru_etl
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python etl.py
python -m streamlit run dashboard/app.py
```

La primera ejecución de `python etl.py` genera los Parquet necesarios para
el dashboard y puede tardar varios minutos por el backfill histórico.

### Windows

```bash
py -3.14 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python etl.py
python -m streamlit run dashboard/app.py
```

**Nota sobre geopandas en Windows**: el proyecto usa `pyogrio` como motor de
lectura geoespacial (no `fiona`), justamente porque `pyogrio` trae wheels
precompilados para Windows y no requiere tener GDAL instalado en el sistema.
Si `pip install -r requirements.txt` falla igual por algún otro paquete,
como alternativa más robusta usa conda:
```bash
conda install -c conda-forge geopandas pandas pyarrow pandera requests
```

## Uso

```bash
python etl.py                                          # normal: backfill 2000->hoy la 1ra vez, incremental después
python etl.py --minmag 6.0                              # sobrescribe magnitud mínima
python etl.py --inicio 2010-01-01 --fin 2010-12-31       # rango manual (ej. reintentar un año que falló)
```

La primera corrida descarga automáticamente el shapefile de GADM Perú
(~28 MB) a `geo/gadm41_PER.gpkg` y lo reutiliza en corridas siguientes
(no se vuelve a descargar).

## Cómo funciona cada capa

### Bronze — backfill inicial + incremental
- **Primera corrida** (sin bronze histórico): trae todo el histórico desde
  el año 2000 (`config.ANIO_INICIO_HISTORICO`) hasta hoy, **año por año**
  (no una sola consulta gigante) para no arriesgar timeouts. Cada año se
  guarda en el parquet apenas se descarga - si un año falla, no se pierde
  el progreso de los años anteriores, y queda logueado exactamente qué
  año reintentar con `python etl.py --inicio YYYY-01-01 --fin YYYY-12-31`.
- **Corridas siguientes**: incremental, solo desde la última fecha cargada
  (guardada en el propio bronze) hasta hoy.
- Se concatena + deduplica por `id` en cada guardado (quedándose con la
  versión más actualizada, porque USGS revisa magnitudes de un mismo
  sismo con el tiempo).
- Si USGS no devuelve sismos en el rango consultado (0 features, algo
  normal y esperable), el ETL detecta bronze vacío y termina limpio sin
  intentar procesar silver/gold.

### Silver — recompute completo, validado y enriquecido
1. Valida el bronze de entrada contra `schema_bronze` (Pandera).
2. Limpia: descarta filas sin campos obligatorios, deduplica de nuevo
   como segunda red de seguridad.
3. **Enriquecimiento geográfico**: convierte lat/lon a `Point` (geopandas)
   y hace un `sjoin` contra la capa MÁS PROFUNDA disponible de GADM
   (idealmente ADM3 = distrito), que trae en cascada `pais`, `departamento`,
   `provincia` y `distrito` en la misma fila — un solo cruce geoespacial
   asigna los 4 niveles a la vez (point-in-polygon exacto, no aproximación
   por bbox). Sismos que caen en el mar (comunes en Perú por la zona de
   subducción - justo ahí ocurren los sismos más grandes, ej. Pisco 2007)
   reciben el departamento/provincia/distrito **más cercano** vía
   `sjoin_nearest`, en vez de quedar sin zona asignada - se agregan las
   columnas `tipo_epicentro` (`"Punto fijo"` = match exacto, `"Mar"` =
   asignado por cercanía) y `distancia_costa_km` (solo poblada para
   `"Mar"`) para que la aproximación quede siempre trazable.
4. Valida el resultado contra `schema_silver` **antes** de optimizar
   memoria (las reglas de negocio importan más que el dtype de storage).
5. Optimiza memoria: downcasting de floats, `category` para strings de
   baja cardinalidad.

### Gold — features y normalización
- `anio`, `mes`, `hora` derivadas de la fecha.
- `magnitud_categoria` / `profundidad_categoria`: binning en escala Richter
  genérica (Leve/Moderado/Fuerte/Muy fuerte/Extremo).
- `dias_desde_ultimo_sismo_mismo_departamento`: recurrencia por zona.
- Tabla de agregaciones separada: conteo y magnitud promedio/máxima por
  departamento-año (distinta granularidad, se une por `(departamento, anio)`
  cuando se necesite).
- `magnitud_zscore_departamento`: **z-score agrupado por departamento**,
  no global. Responde a "qué tan inusual es este sismo para el historial
  propio de ESE departamento" — ver notas del proyecto para el razonamiento
  completo de por qué no se usa z-score global sobre la magnitud.

## Logging

Un archivo por día en `logs/`, con: inicio/fin de cada capa, filas
procesadas/escritas, duplicados eliminados, errores específicos con
traceback (cada función tiene su propio try/except, no un solo try
global), y qué regla de Pandera falló si aplica.

Exit codes de `etl.py`: `0` éxito, `1` error bronze/API, `2` error silver,
`3` error gold, `4` error inesperado no controlado.

## Automatizar en Windows (Task Scheduler)

Acción -> Iniciar programa -> `run_daily.bat`. Directorio de inicio: la
carpeta del proyecto.

## Librerías utilizadas y para qué sirve cada una

| Librería | Dónde se usa | Qué hace / por qué la necesitamos |
|---|---|---|
| `pandas` | Todo el proyecto | Manipulación de DataFrames: groupby, merge, dedup, binning, transformaciones. |
| `pyarrow` | `*/writer.py` | Motor de lectura/escritura de `.parquet` (formato columnar comprimido). |
| `requests` | `bronze/api_client.py`, `silver/geo_enrichment.py` | Llamadas HTTP a la API de USGS y descarga del `.gpkg` de GADM. |
| `pandera` | `silver/schemas.py` | Validación automatizada de reglas de negocio (rangos, nulos, tipos) - detecta datos corruptos antes de que lleguen a gold. |
| `geopandas` | `silver/geo_enrichment.py` | Point-in-polygon (`sjoin`) para asignar pais/departamento/provincia/distrito según lat/lon real. |
| `pyogrio` | `silver/geo_enrichment.py` | Motor de lectura de `.gpkg`/`.shp` que usa geopandas. Reemplaza a `fiona` - no requiere GDAL instalado en el sistema (evita el error de compilación en Windows). |
| `shapely` | usado internamente por geopandas | Representa las geometrías (`Point`, `Polygon`) y hace el cálculo matemático de "¿está este punto dentro de este polígono?". |
| `pathlib` (estándar) | `config.py` | Manejo de rutas multiplataforma (Windows/Linux) sin problemas de `/` vs `\`. |
| `datetime` (estándar) | `bronze/api_client.py`, `etl.py` | Cálculo de fechas: hoy, rango incremental, años del backfill. |
| `logging` (estándar) | `logger_setup.py` y todos los módulos | Sistema de logs diario a archivo + consola. |
| `argparse` (estándar) | `etl.py` | Parseo de argumentos de línea de comandos (`--minmag`, `--inicio`, `--fin`). |
| `streamlit` | `dashboard/app.py` | Framework del dashboard interactivo - filtros, tabs, KPIs, sin necesidad de escribir HTML/JS. |
| `plotly` | `dashboard/app.py` | Gráficos interactivos (líneas, barras, mapas, scatter) con zoom y hover, integrados nativamente con Streamlit. |

## Cómo funciona este proyecto (explicado simple)

Este es un proyecto de ETL (Extract, Transform, Load) que arma un histórico
de sismos en Perú, listo para hacer análisis: evolución de magnitud por
región a lo largo de los años, qué zonas tienen más actividad sísmica, y
qué tan inusual es un sismo comparado con el historial de su propia zona.

La idea de fondo es simple: cada vez que corro `python etl.py`, el sistema
va a la API pública de USGS (el servicio geológico de EE.UU. que registra
sismos de todo el mundo en tiempo real), trae los sismos nuevos de Perú, y
los procesa en 3 pasos hasta dejarlos listos para análisis o para un
dashboard.

Uso una **arquitectura medallón** (un patrón bastante estándar en ingeniería
de datos), que separa el trabajo en 3 "capas" con responsabilidades claras:

- **Bronze** (dato crudo): tal como llega de la API, sin tocar nada. Es mi
  respaldo - si algo sale mal en los pasos siguientes, siempre puedo volver
  a procesar desde acá sin tener que consultarle a la API de nuevo.
- **Silver** (dato limpio y confiable): acá se valida que los datos tengan
  sentido (magnitudes en rango válido, sin duplicados, sin nulos donde no
  debería haberlos), y se le agrega contexto geográfico - a qué país,
  departamento, provincia y distrito pertenece cada sismo, cruzando las
  coordenadas contra mapas reales.
- **Gold** (dato listo para análisis): acá calculo las variables que
  realmente me interesan para responder preguntas - en qué categoría de
  magnitud cae cada sismo, cuánto pasó desde el último sismo en esa misma
  zona, y qué tan atípico fue comparado con el historial de esa zona
  específica.

Cada capa queda guardada en su propio archivo (`.parquet`, un formato
eficiente para datos tabulares), y cada corrida deja un registro detallado
en `logs/` de qué se procesó y si algo falló.

La primera vez que se corre, el sistema trae automáticamente todo el
histórico disponible desde el año 2000. Las corridas siguientes son
incrementales: solo trae los sismos nuevos desde la última vez que se
ejecutó, sin tener que volver a descargar todo de nuevo.

## Dashboard (Streamlit)

```bash
streamlit run dashboard/app.py
```

### Cinco preguntas de negocio

1. **¿Qué departamentos concentran la mayor actividad sísmica?**
2. **¿Cuáles fueron los sismos de mayor magnitud?**
3. **¿Cómo evolucionaron la frecuencia y la magnitud a través del tiempo?**
4. **¿Dónde se concentran geográficamente los eventos?**
5. **¿Qué eventos se alejan del patrón esperado de magnitud y frecuencia?**

Cada pregunta aparece explícitamente en el dashboard y se responde con una
visualización interactiva. La quinta combina la distribución de magnitudes con
el z-score por departamento para identificar eventos atípicos.

### Enlaces de entrega

- **Repositorio público:** https://github.com/ManuelFanola/sismos_peru_etl
- **Dashboard en Streamlit Cloud:** `PENDIENTE: pegar aquí el enlace público después del despliegue`

> Antes de entregar, reemplaza el texto pendiente por la URL real con formato
> `https://<nombre-app>.streamlit.app`. El enlace no se puede generar solamente
> modificando el código: se debe publicar desde una cuenta de Streamlit Cloud.

Filtros disponibles en la barra lateral, todos como listas de selección
(multiselect) — sin selección = sin filtrar esa dimensión:

- **País**, **Departamento**, **Provincia**, **Distrito** — en cascada:
  las opciones de Provincia se acotan al/los departamento(s) elegido(s),
  y las de Distrito a la provincia (o departamento) elegida. Refleja la
  jerarquía administrativa real de Perú (departamento/provincia
  constitucional del Callao → provincia → distrito).
- **Año**, **Mes**, **Semana del año (ISO)**, **Hora del día** — todos
  como multiselect (no rango), para poder elegir valores puntuales no
  contiguos (ej. solo enero y julio, o solo semana 5 y semana 30).
- **Tipo de magnitud** (`mag_type`: mb/mww/mwc/etc.) — útil porque `mww`/`mwc`
  son más precisos en sismos grandes que `mb` (ver limitación 2.3 del informe).
- **Magnitud mínima (≥)** — slider numérico (no lista), para ver por
  ejemplo solo sismos de magnitud 6.0 o mayor. Distinto del filtro de
  `Tipo de magnitud`: este es un umbral sobre el valor numérico.
- **Tipo de epicentro** (`Punto fijo` / `Mar`) — para aislar los sismos
  cuyo departamento fue asignado por cercanía (offshore) de los que
  matchearon un polígono real.

La columna `semana` no viene persistida en gold - se calcula al vuelo al
cargar los datos (`dashboard/data_loader.py`), así que no hace falta
re-correr el ETL para tenerla disponible.

**El z-score se recalcula dinámicamente** después de aplicar los filtros
(no usa el valor fijo que ya viene en gold) - así, si filtras por año,
departamento, tipo de magnitud, etc., cada sismo se compara contra el
historial ya filtrado de su propio departamento, manteniendo el número
coherente con lo que estás viendo en pantalla.

Pestañas:
- **Ranking**: con drill-down jerárquico automático — vista por
  departamento si no hay selección específica; por provincia si se
  eligió 1 departamento; por distrito si se eligió 1 provincia.
- **Detalle / Tabla**: cada sismo individual (no promedios) - scatter de
  magnitud en el tiempo + tabla completa ordenable (por magnitud o por
  fecha) con botón de descarga a CSV. Pensada para responder "¿cuáles
  fueron los sismos más grandes?", que las vistas agregadas no muestran.
- **Evolución temporal**: magnitud promedio por año (con cantidad de
  sismos visible en el hover), cantidad de sismos por año segmentada por
  departamento (con el **total siempre visible** arriba de cada barra,
  no solo al pasar el mouse), magnitud promedio por hora del día, y una
  tabla resumen de todos los departamentos.
- **Mapa**: ubicación geográfica interactiva, coloreable por categoría de magnitud o por z-score.
- **Magnitud/Frecuencia**: distribución de magnitud (Gutenberg-Richter), por `mag_type`, y un diccionario explicando qué significa cada tipo de magnitud (mb/ml/ms/md/mww/mwc/mwb/mwr/m).
- **Z-score / Atípicos**: sismos inusuales respecto al historial de su propia zona, con umbral ajustable.

Cada pestaña incluye advertencias inline sobre las limitaciones conocidas
del proyecto (ver informe de problemas de arquitectura y reglas de negocio).

### Actualizar los datos sin salir del dashboard

Hay un botón **"🔄 Actualizar datos (correr ETL)"** al inicio de la barra
lateral. Corre `etl.py` como un subproceso aparte (no en el mismo proceso
de Streamlit, para no arriesgar tumbar el servidor si el ETL falla) y,
si termina bien, recarga automáticamente el dashboard con los datos
nuevos. Si falla, muestra el motivo y el log completo en un panel
expandible, sin romper el resto del dashboard. Una actualización
incremental normal tarda segundos; si nunca corriste el ETL antes (o
faltan varios días), puede tardar más.

## Próximos pasos

- Dashboard en Streamlit sobre `data/gold/sismos_features.parquet` y
  `data/gold/sismos_agregaciones_departamento_anio.parquet`. **(Implementado, ver sección arriba)**
- Extender `geo_enrichment.py` a nivel provincia/distrito (ADM2/ADM3) si
  se necesita mayor granularidad geográfica. **(Implementado)**
- Expandir el bbox de `config.py` para incluir otros países (GADM ya
  soporta esto sin cambiar de librería).