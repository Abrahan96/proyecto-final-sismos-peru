"""
dashboard/app.py
Dashboard interactivo de sismos en Perú (arquitectura medallón - capa gold).

Uso:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import subprocess
import sys

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_loader import (
    cargar_gold, cargar_agregaciones, recalcular_zscore, aplicar_filtros,
    opciones_provincia, opciones_distrito, MESES_NOMBRE,
)
from config import BASE_DIR

st.set_page_config(
    page_title="Sismos Perú",
    page_icon="🌎",
    layout="wide",
)

COLOR_MAGNITUD = {
    "Leve": "#2ecc71",
    "Moderado": "#f1c40f",
    "Fuerte": "#e67e22",
    "Muy fuerte": "#e74c3c",
    "Extremo": "#8e44ad",
}

# --------------------------------------------------------------------
# Botón: correr el ETL (bronze -> silver -> gold) sin salir del dashboard
# --------------------------------------------------------------------
def ejecutar_etl_y_recargar(ui) -> None:
    """
    Corre etl.py como subproceso aparte (NO se importa/llama en el mismo
    proceso: etl.py hace sys.exit() al terminar, lo que mataría también al
    servidor de Streamlit si se llamara directo). Al terminar OK, limpia el
    cache de datos y recarga el dashboard con lo nuevo.

    ui: st o st.sidebar, según desde dónde se llamó (para que el spinner y
    los mensajes aparezcan en el lugar correcto).
    """
    with ui.spinner(
        "Corriendo el pipeline completo (bronze → silver → gold)... "
        "una actualización incremental normal tarda segundos; la primera vez "
        "(backfill histórico desde el año 2000) puede tardar varios minutos."
    ):
        resultado = subprocess.run(
            [sys.executable, str(BASE_DIR / "etl.py")],
            capture_output=True, text=True, cwd=str(BASE_DIR),
        )

    if resultado.returncode == 0:
        ui.success("✅ Datos actualizados correctamente.")
        cargar_gold.clear()
        cargar_agregaciones.clear()
        st.rerun()
    else:
        ui.error(f"❌ El ETL terminó con error (código de salida {resultado.returncode}).")
        with ui.expander("Ver detalle del error"):
            salida = (resultado.stdout or "") + "\n" + (resultado.stderr or "")
            st.code(salida[-4000:] or "(sin salida capturada)", language=None, wrap_lines=True)

# --------------------------------------------------------------------
# Carga de datos
# --------------------------------------------------------------------
df_gold = cargar_gold()

if df_gold.empty:
    st.error(
        "No se encontró data en `data/gold/`. Corre el ETL para generar los "
        "datos por primera vez (si nunca corrió, trae el histórico completo "
        "desde el año 2000 - puede tardar varios minutos)."
    )
    if st.button("🔄 Correr ETL ahora"):
        ejecutar_etl_y_recargar(st)
    st.stop()

# --------------------------------------------------------------------
# Sidebar - filtros
# --------------------------------------------------------------------
st.sidebar.title("🌎 Filtros")

if st.sidebar.button("🔄 Actualizar datos", width="stretch"):
    ejecutar_etl_y_recargar(st.sidebar)
st.sidebar.caption(
    "Trae los sismos nuevos desde USGS y recalcula todo. Una actualización "
    "normal (incremental) tarda segundos."
)

st.sidebar.divider()

paises_disp = sorted(df_gold["pais"].dropna().unique().tolist())
paises_sel = st.sidebar.multiselect("País", paises_disp, default=paises_disp)

deptos_disp = sorted(df_gold["departamento"].dropna().unique().tolist())
deptos_sel = st.sidebar.multiselect("Departamento", deptos_disp, default=[])

# Provincia y Distrito en cascada: las opciones se acotan según lo ya elegido arriba
provincias_disp = opciones_provincia(df_gold, deptos_sel)
provincias_sel = st.sidebar.multiselect(
    "Provincia", provincias_disp, default=[],
    help="Opciones acotadas al/los departamento(s) seleccionado(s) arriba.",
)

distritos_disp = opciones_distrito(df_gold, deptos_sel, provincias_sel)
distritos_sel = st.sidebar.multiselect(
    "Distrito", distritos_disp, default=[],
    help="Opciones acotadas a la provincia (o departamento) seleccionada arriba.",
)

st.sidebar.divider()

anios_disp = sorted(df_gold["anio"].dropna().unique().tolist())
anios_sel = st.sidebar.multiselect("Año", anios_disp, default=[])

meses_sel = st.sidebar.multiselect(
    "Mes", options=list(MESES_NOMBRE.keys()),
    format_func=lambda m: MESES_NOMBRE[m], default=[],
)

semanas_sel = st.sidebar.multiselect(
    "Semana del año (ISO)", options=list(range(1, 54)), default=[],
    help="Sin selección = todas las semanas. Puedes elegir semanas puntuales no contiguas.",
)

horas_sel = st.sidebar.multiselect(
    "Hora del día (UTC)", options=list(range(24)), default=[],
    help="Sin selección = todas las horas. Puedes elegir horas puntuales no contiguas.",
)

st.sidebar.divider()

magtype_disp = sorted(df_gold["mag_type"].dropna().unique().tolist())
magtype_sel = st.sidebar.multiselect(
    "Tipo de magnitud", magtype_disp, default=[],
    help="mww/mwc = magnitud de momento (más precisa en sismos grandes). mb = ondas de cuerpo, puede subestimar sismos >6.5.",
)

mag_min_dato = float(df_gold["magnitud"].min())
mag_max_dato = float(df_gold["magnitud"].max())
magnitud_minima = st.sidebar.slider(
    "Magnitud mínima (≥)", mag_min_dato, mag_max_dato, mag_min_dato, step=0.1,
    help="Ej. mueve a 6.0 para ver solo sismos de magnitud 6 o mayor, en el gráfico y en la tabla.",
)

tipo_epicentro_sel = st.sidebar.multiselect(
    "Tipo de epicentro", ["Punto fijo", "Mar"], default=[],
    help=(
        "'Punto fijo' = el epicentro cayó dentro de un departamento/distrito real. "
        "'Mar' = epicentro offshore, se le asignó la zona terrestre más cercana "
        "(común en los sismos más grandes de Perú, por la zona de subducción)."
    ),
)

st.sidebar.caption(
    "El z-score de magnitud se recalcula automáticamente según los filtros "
    "aplicados, comparando cada sismo contra el historial filtrado de su "
    "propio departamento - no contra el histórico completo sin filtrar."
)

# --------------------------------------------------------------------
# Aplicar filtros + recalcular z-score sobre el subconjunto filtrado
# --------------------------------------------------------------------
df_filtrado = aplicar_filtros(
    df_gold, paises_sel, deptos_sel, provincias_sel, distritos_sel,
    anios_sel, meses_sel, semanas_sel, horas_sel, magtype_sel, magnitud_minima,
    tipo_epicentro_sel,
)
df_filtrado = recalcular_zscore(df_filtrado)

st.title("Sismos en Perú")
st.caption(
    f"Fuente: USGS · magnitud ≥ 4.5 · {len(df_filtrado):,} sismos en la selección actual "
    f"(de {len(df_gold):,} totales)"
)

st.subheader("5 preguntas de negocio")
st.markdown(
    """
1. **¿Qué departamentos concentran la mayor actividad sísmica?** → pestaña *Ranking*.
2. **¿Cuáles fueron los sismos de mayor magnitud?** → pestaña *Detalle / Tabla*.
3. **¿Cómo evolucionaron la frecuencia y la magnitud a través del tiempo?** → pestaña *Evolución temporal*.
4. **¿Dónde se concentran geográficamente los eventos?** → pestaña *Mapa*.
5. **¿Qué eventos se alejan del patrón esperado de magnitud y frecuencia?** → pestañas *Magnitud/Frecuencia* y *Z-score / Atípicos*.
"""
)

if df_filtrado.empty:
    st.warning("No hay sismos que coincidan con los filtros seleccionados.")
    st.stop()

# --------------------------------------------------------------------
# KPIs
# --------------------------------------------------------------------
col1, col2, col3 = st.columns(3)
col1.metric("🌎 Total de sismos", f"{len(df_filtrado):,}")
col2.metric("📈 Magnitud promedio", f"{df_filtrado['magnitud'].mean():.2f}")
col3.metric("🔥 Magnitud máxima", f"{df_filtrado['magnitud'].max():.1f}")

col4, col5, col6 = st.columns(3)
col4.metric("📉 Magnitud mínima", f"{df_filtrado['magnitud'].min():.1f}")
col5.metric("⬇️ Profundidad promedio", f"{df_filtrado['profundidad_km'].mean():.0f} km")
depto_top = (
    df_filtrado["departamento"].value_counts().idxmax()
    if df_filtrado["departamento"].notna().any() else "N/A"
)
col6.metric("🏆 Departamento más activo", depto_top)

with st.expander("ℹ️ Qué significa cada indicador"):
    st.markdown(
        """
| Indicador | Descripción |
|---|---|
| 🌎 Total de sismos | Número total de registros en la selección actual |
| 📈 Magnitud promedio | Promedio de `magnitud` de todos los sismos filtrados |
| 🔥 Magnitud máxima | Valor más alto de `magnitud` registrado en la selección |
| 📉 Magnitud mínima | Valor más bajo de `magnitud` registrado en la selección |
| ⬇️ Profundidad promedio | Promedio de `profundidad_km` (qué tan cerca de la superficie, en general) |
| 🏆 Departamento más activo | Departamento con más sismos dentro de los filtros aplicados |
"""
    )

sismos_mar = (df_filtrado["tipo_epicentro"] == "Mar").sum()
if sismos_mar > 0:
    dist_prom = df_filtrado.loc[df_filtrado["tipo_epicentro"] == "Mar", "distancia_costa_km"].mean()
    st.info(
        f"🌊 {sismos_mar} sismos en la selección actual tienen epicentro en el mar. "
        f"Se les asignó el departamento/provincia/distrito más cercano (distancia promedio: "
        f"{dist_prom:.0f} km) para que no queden invisibles en los gráficos agrupados por zona - "
        f"pero es una aproximación por cercanía, no la ubicación real del evento. "
        f"Usa el filtro 'Tipo de epicentro' en la barra lateral para aislarlos."
    )

sin_zona = df_filtrado["departamento"].isna().sum()
if sin_zona > 0:
    st.warning(
        f"⚠️ {sin_zona} sismos no tienen ningún departamento asignado (ni exacto ni por "
        f"cercanía) - revisa si el shapefile de GADM cubre bien esa zona."
    )

# --------------------------------------------------------------------
# Tabs
# --------------------------------------------------------------------
tab_ranking, tab_detalle, tab_evolucion, tab_mapa, tab_frecuencia, tab_zscore = st.tabs(
    ["🏆 Ranking", "📋 Detalle / Tabla", "📈 Evolución temporal", "🗺️ Mapa", "📊 Magnitud/Frecuencia", "⚡ Z-score / Atípicos"]
)

# --- Ranking ---
with tab_ranking:
    st.header("1. ¿Qué departamentos concentran la mayor actividad sísmica?")
    # Drill-down jerárquico según lo seleccionado en la cascada de la sidebar:
    # 1 provincia elegida -> desglosa por distrito
    # 1 departamento elegido (sin provincia específica) -> desglosa por provincia
    # nada específico elegido -> vista general por departamento
    if len(provincias_sel) == 1:
        columna_agrupacion, etiqueta_col = "distrito", "Distrito"
        titulo_extra = f"{provincias_sel[0]} ({deptos_sel[0] if deptos_sel else ''})"
    elif len(deptos_sel) == 1:
        columna_agrupacion, etiqueta_col = "provincia", "Provincia"
        titulo_extra = deptos_sel[0]
    else:
        columna_agrupacion, etiqueta_col = "departamento", "Departamento"
        titulo_extra = None

    if titulo_extra:
        st.subheader(f"Sismos por {etiqueta_col.lower()} — {titulo_extra}")
    else:
        st.subheader("Sismos por departamento")
        st.caption(
            "Selecciona un departamento para ver el desglose por provincia, "
            "o una provincia para ver el desglose por distrito."
        )

    conteo = df_filtrado[columna_agrupacion].value_counts()
    conteo = conteo[conteo > 0].sort_values()  # dtype category retiene categorías con 0 tras filtrar
    fig = px.bar(
        conteo, orientation="h", text=conteo.values,
        labels={"value": "Cantidad de sismos", "index": etiqueta_col},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False, height=max(400, len(conteo) * 28))
    st.plotly_chart(fig, width="stretch")

    st.subheader(f"Segmentado por categoría de magnitud ({etiqueta_col.lower()})")
    tabla_cat = (
        df_filtrado.groupby([columna_agrupacion, "magnitud_categoria"], observed=True)
        .size().reset_index(name="cantidad")
    )
    fig2 = px.bar(
        tabla_cat, x="cantidad", y=columna_agrupacion, color="magnitud_categoria",
        orientation="h", color_discrete_map=COLOR_MAGNITUD, text="cantidad",
        category_orders={"magnitud_categoria": list(COLOR_MAGNITUD.keys())},
    )
    fig2.update_traces(textposition="inside")
    fig2.update_layout(height=max(400, tabla_cat[columna_agrupacion].nunique() * 28))
    st.plotly_chart(fig2, width="stretch")

# --- Detalle / Tabla ---
with tab_detalle:
    st.header("2. ¿Cuáles fueron los sismos de mayor magnitud?")
    st.subheader("Todos los sismos en la selección actual")
    st.caption(
        "Vista de detalle (no promedios): cada fila es un sismo individual. "
        "Usa el filtro de 'Magnitud mínima' en la barra lateral para ver, por "
        "ejemplo, solo los sismos de magnitud 6.0 o mayor."
    )

    orden_por = st.radio(
        "Ordenar por", ["Magnitud (mayor primero)", "Fecha (más reciente primero)"],
        horizontal=True,
    )
    if orden_por == "Magnitud (mayor primero)":
        df_tabla = df_filtrado.sort_values("magnitud", ascending=False)
    else:
        df_tabla = df_filtrado.sort_values("fecha_hora_utc", ascending=False)

    # Gráfico: cada sismo individual en el tiempo, tamaño/color por magnitud -
    # a diferencia de la pestaña Evolución (que muestra promedios), acá se ve
    # cada evento por separado, así los picos (los sismos más grandes) saltan
    # a la vista en vez de quedar diluidos en un promedio anual.
    fig = px.scatter(
        df_filtrado, x="fecha_hora_utc", y="magnitud",
        color="magnitud_categoria", size="magnitud",
        color_discrete_map=COLOR_MAGNITUD,
        category_orders={"magnitud_categoria": list(COLOR_MAGNITUD.keys())},
        hover_data=["departamento", "distrito", "mag_type", "profundidad_km"],
        labels={"fecha_hora_utc": "Fecha", "magnitud": "Magnitud"},
    )
    st.plotly_chart(fig, width="stretch")

    st.write(f"**{len(df_tabla):,}** sismos en la tabla.")

    columnas_tabla = [
        "id", "fecha_hora_utc", "pais", "departamento", "provincia", "distrito",
        "tipo_epicentro", "distancia_costa_km",
        "magnitud", "magnitud_categoria", "mag_type", "profundidad_km",
        "profundidad_categoria", "magnitud_zscore_departamento", "lugar",
    ]
    st.dataframe(
        df_tabla[columnas_tabla],
        width="stretch",
        height=500,
        column_config={
            "magnitud": st.column_config.NumberColumn(format="%.1f"),
            "magnitud_zscore_departamento": st.column_config.NumberColumn(format="%.2f"),
            "profundidad_km": st.column_config.NumberColumn(format="%.1f km"),
            "distancia_costa_km": st.column_config.NumberColumn(format="%.1f km"),
        },
    )

    st.download_button(
        "⬇️ Descargar tabla filtrada (CSV)",
        data=df_tabla[columnas_tabla].to_csv(index=False).encode("utf-8"),
        file_name="sismos_filtrados.csv",
        mime="text/csv",
    )


with tab_evolucion:
    st.header("3. ¿Cómo evolucionaron la frecuencia y la magnitud a través del tiempo?")
    st.subheader("Magnitud promedio por año")
    top_n = st.slider("Mostrar top N departamentos por cantidad de sismos", 3, 15, 6, key="topn_evol")
    conteo_deptos = df_filtrado["departamento"].value_counts()
    conteo_deptos = conteo_deptos[conteo_deptos > 0]  # excluir categorías con 0 tras filtrar
    top_deptos = conteo_deptos.head(top_n).index.tolist()

    # Colores fijos por departamento, reutilizados en los 2 gráficos de abajo -
    # así el mismo departamento tiene el mismo color en ambos, y darle click a
    # una leyenda para aislar/ocultar un departamento se puede hacer en los dos
    # gráficos de forma consistente (Plotly no sincroniza el click entre
    # gráficos distintos automáticamente, pero al menos el color coincide).
    paleta = px.colors.qualitative.Plotly
    colores_deptos = {depto: paleta[i % len(paleta)] for i, depto in enumerate(top_deptos)}

    evol = (
        df_filtrado[df_filtrado["departamento"].isin(top_deptos)]
        .groupby(["departamento", "anio"], observed=True)["magnitud"]
        .agg(magnitud="mean", n_sismos="count")
        .astype({"magnitud": "float64"}).round({"magnitud": 1}).reset_index()
    )
    fig = px.line(
        evol, x="anio", y="magnitud", color="departamento", markers=True, text="magnitud",
        color_discrete_map=colores_deptos, hover_data={"n_sismos": True},
        labels={"anio": "Año", "magnitud": "Magnitud promedio", "n_sismos": "Sismos ese año"},
    )
    fig.update_traces(textposition="top center")
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Pasa el mouse sobre cada punto para ver cuántos sismos entraron en ese "
        "promedio (`n_sismos`) - un promedio de 2 eventos no es tan confiable como "
        "uno de 20. Si se ve saturado de etiquetas, reduce el 'top N' de arriba."
    )

    st.subheader("Cantidad de sismos por año, por departamento")
    conteo_anual = (
        df_filtrado[df_filtrado["departamento"].isin(top_deptos)]
        .groupby(["anio", "departamento"], observed=True).size().reset_index(name="cantidad")
    )
    fig2 = px.bar(
        conteo_anual, x="anio", y="cantidad", color="departamento",
        color_discrete_map=colores_deptos,
        labels={"anio": "Año", "cantidad": "Sismos", "departamento": "Departamento"},
    )

    # Etiqueta de TOTAL siempre visible arriba de cada barra (no por segmento -
    # el detalle de cada departamento se sigue viendo solo al pasar el mouse).
    # Truco: una traza de texto invisible (sin barra/línea) posicionada en la
    # altura total de cada barra apilada.
    totales_por_anio = conteo_anual.groupby("anio")["cantidad"].sum().reset_index()
    fig2.add_trace(go.Scatter(
        x=totales_por_anio["anio"], y=totales_por_anio["cantidad"],
        mode="text", text=totales_por_anio["cantidad"], textposition="top center",
        textfont=dict(size=13), showlegend=False, hoverinfo="skip",
    ))
    fig2.update_yaxes(range=[0, totales_por_anio["cantidad"].max() * 1.15])

    st.plotly_chart(fig2, width="stretch")
    st.caption(
        "El número sobre cada barra es el total de sismos ese año (suma de los "
        "departamentos mostrados - si reduces el 'top N' de arriba, el total "
        "también baja, porque deja de incluir a los departamentos ocultos). "
        "Mismos colores por departamento que el gráfico de arriba. Haz click en un "
        "departamento de la leyenda para ocultarlo/aislarlo (funciona de forma "
        "independiente en cada gráfico, Plotly no sincroniza el click entre gráficos distintos)."
    )

    st.subheader("Magnitud promedio por hora del día (UTC)")
    por_hora = (
        df_filtrado.groupby("hora")["magnitud"]
        .agg(magnitud="mean", n_sismos="count")
        .astype({"magnitud": "float64"}).round({"magnitud": 2}).reset_index()
    )
    fig3 = px.bar(
        por_hora, x="hora", y="magnitud", text="magnitud",
        hover_data={"n_sismos": True},
        labels={"hora": "Hora del día (UTC)", "magnitud": "Magnitud promedio", "n_sismos": "Sismos en esa hora"},
    )
    fig3.update_traces(textposition="outside")
    fig3.update_xaxes(dtick=1)
    st.plotly_chart(fig3, width="stretch")
    st.caption(
        "Es un patrón puramente estadístico, no físico: la hora del día no causa "
        "sismos más o menos fuertes. Horas con pocos sismos (revisa `n_sismos` en "
        "el hover) pueden mostrar promedios poco representativos."
    )

    st.subheader("Top departamentos (resumen completo)")
    top_tabla = (
        df_filtrado.groupby("departamento", observed=True)
        .agg(
            sismos_total=("id", "count"),
            magnitud_promedio=("magnitud", "mean"),
            magnitud_maxima=("magnitud", "max"),
            magnitud_minima=("magnitud", "min"),
            profundidad_promedio_km=("profundidad_km", "mean"),
        )
        .astype({
            "magnitud_promedio": "float64", "magnitud_maxima": "float64",
            "magnitud_minima": "float64", "profundidad_promedio_km": "float64",
        })
        .round(1)
        .sort_values("sismos_total", ascending=False)
        .reset_index()
    )
    st.dataframe(
        top_tabla,
        width="stretch",
        column_config={
            "departamento": "Departamento",
            "sismos_total": "Sismos totales",
            "magnitud_promedio": st.column_config.NumberColumn("Magnitud promedio", format="%.1f"),
            "magnitud_maxima": st.column_config.NumberColumn("Magnitud máxima", format="%.1f"),
            "magnitud_minima": st.column_config.NumberColumn("Magnitud mínima", format="%.1f"),
            "profundidad_promedio_km": st.column_config.NumberColumn("Profundidad promedio", format="%.0f km"),
        },
        hide_index=True,
    )

# --- Mapa ---
with tab_mapa:
    with st.expander("📖 ¿Cual es el umbral  cada categoria?"):
        st.markdown(
        """

    | Categoría | Rango de Magnitud | Descripción y Efectos Estimados |
    | :--- | :--- | :--- |
    | **Leve** | 0.0 a 4.5 | Generalmente percibido por la población en los niveles más altos, pero rara vez causa daños estructurales. |
    | **Moderado** | Mayor a 4.5 hasta 5.5 | Se siente con claridad en interiores y exteriores. Puede causar daños menores en edificaciones vulnerables. |
    | **Fuerte** | Mayor a 5.5 hasta 6.5 | Capaz de provocar daños severos en estructuras deficientes o antiguas dentro de un radio moderado. |
    | **Muy fuerte** | Mayor a 6.5 hasta 7.5 | Causa daños graves en comunidades extensas y puede provocar colapsos en infraestructuras no preparadas. |
    | **Extremo** | Mayor a 7.5 hasta 10.0 | Devastación total en áreas grandes cerca del epicentro, con pérdidas materiales masivas e impacto regional. |


    """
    )
    st.header("4. ¿Dónde se concentran geográficamente los eventos?")
    st.subheader("Ubicación geográfica de los sismos")
    color_por = st.radio(
        "Colorear por", ["magnitud_categoria", "magnitud_zscore_departamento"],
        format_func=lambda x: "Categoría de magnitud" if x == "magnitud_categoria" else "Z-score (atípico)",
        horizontal=True,
    )

    if color_por == "magnitud_categoria":
        fig = px.scatter_map(
            df_filtrado, lat="latitud", lon="longitud", size="magnitud",
            color="magnitud_categoria", color_discrete_map=COLOR_MAGNITUD,
            category_orders={"magnitud_categoria": list(COLOR_MAGNITUD.keys())},
            hover_data=["departamento", "distrito", "anio", "magnitud", "mag_type"],
            zoom=4, height=650,
        )
    else:
        fig = px.scatter_map(
            df_filtrado, lat="latitud", lon="longitud",
            size=df_filtrado["magnitud_zscore_departamento"].abs().fillna(0),
            color="magnitud_zscore_departamento", color_continuous_scale="RdBu_r",
            range_color=[-3, 3],
            hover_data=["departamento", "distrito", "anio", "magnitud"],
            zoom=4, height=650,
        )

    fig.update_layout(map_style="open-street-map", margin={"r": 0, "t": 0, "l": 0, "b": 0})
    st.plotly_chart(fig, width="stretch")

# --- Magnitud / Frecuencia ---
with tab_frecuencia:
    st.header("5. ¿Qué eventos se alejan del patrón esperado de magnitud y frecuencia?")
    st.subheader("Distribución de magnitud")
    fig = px.histogram(
        df_filtrado, x="magnitud", nbins=30, text_auto=True,
        labels={"magnitud": "Magnitud", "count": "Cantidad de sismos"},
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "A mayor magnitud, menor frecuencia - patrón esperado (Ley de Gutenberg-Richter). "
        "Nota: sin declustering de réplicas, un sismo grande con muchas réplicas puede "
        "inflar el conteo de magnitudes bajas en su misma zona/período."
    )

    st.subheader("Distribución por tipo de magnitud (mag_type)")
    fig2 = px.histogram(df_filtrado, x="magnitud", color="mag_type", nbins=30, barmode="overlay", opacity=0.6)
    st.plotly_chart(fig2, width="stretch")
    st.caption(
        "mb tiende a subestimar sismos grandes (>6.5) frente a mww/mwc. "
        "Ten esto en cuenta al comparar magnitudes entre eventos de distinto mag_type."
    )

    with st.expander("📖 ¿Qué significa cada tipo de magnitud?"):
        st.markdown(
            """
| Código | Nombre | Qué mide |
|---|---|---|
| `mb` | Magnitud de ondas de cuerpo | Amplitud de las ondas P; común en reportes rápidos/automáticos. Subestima sismos grandes (>6.5) |
| `ml` | Magnitud local (Richter) | La escala clásica de Richter (1935); amplitud cerca del epicentro |
| `ms` | Magnitud de ondas superficiales | Amplitud de ondas superficiales; usada históricamente para sismos moderados-grandes |
| `md` | Magnitud de duración (coda) | Duración de la señal sísmica registrada; común en sismos pequeños |
| `mww` | Momento sísmico, método W-phase | Estándar de USGS para sismos M5.0+ (confiable desde M5.5). No se satura en sismos grandes |
| `mwc` | Momento sísmico, método centroide (CMT) | Similar a `mww`, calculado con tensor de momento centroide |
| `mwb` | Momento sísmico, ondas P de banda ancha | Estimación de momento sísmico a partir de ondas P de banda ancha |
| `mwr` | Momento sísmico, distancia regional | Estimación de momento sísmico con redes sismológicas regionales |
| `m` | Magnitud genérica | Método de cálculo no especificado en el catálogo de origen |

`mww`, `mwc`, `mwb` y `mwr` son todas variantes del **momento sísmico (Mw)** - miden
la energía física liberada directamente, a diferencia de `mb`/`ml`/`ms` que miden
amplitud de onda y pueden "saturarse" (dejar de crecer) en sismos muy grandes.
"""
        )

# --- Z-score / Atípicos ---
with tab_zscore:
    st.header("5. Eventos atípicos: complemento estadístico")
    st.subheader("Sismos atípicos según el historial de su propio departamento")
    umbral = st.slider("Umbral de |z-score| para considerar atípico", 1.0, 4.0, 2.0, 0.1)

    atipicos = df_filtrado[df_filtrado["magnitud_zscore_departamento"].abs() >= umbral]
    st.write(f"**{len(atipicos)}** sismos con |z-score| ≥ {umbral} en la selección actual.")

    df_plot = df_filtrado.copy()
    es_atipico = df_plot["magnitud_zscore_departamento"].abs() >= umbral
    # .astype(str) es necesario porque 'departamento' es dtype category (optimizado en
    # silver/optimization.py) - .where() no puede insertar "" si no es una categoría existente.
    df_plot["_etiqueta"] = df_plot["departamento"].astype(str).where(es_atipico, "")

    fig = px.scatter(
        df_plot, x="fecha_hora_utc", y="magnitud_zscore_departamento",
        color=es_atipico, text="_etiqueta",
        color_discrete_map={True: "#e74c3c", False: "#bdc3c7"},
        hover_data=["departamento", "distrito", "magnitud"],
        labels={"fecha_hora_utc": "Fecha", "magnitud_zscore_departamento": "Z-score"},
    )
    fig.update_traces(textposition="top center")
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.add_hline(y=umbral, line_dash="dot", line_color="orange")
    fig.add_hline(y=-umbral, line_dash="dot", line_color="orange")
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, width="stretch")

    st.dataframe(
        atipicos[[
            "id", "fecha_hora_utc", "departamento", "distrito", "magnitud",
            "mag_type", "profundidad_km", "magnitud_zscore_departamento",
        ]].sort_values("magnitud_zscore_departamento", key=abs, ascending=False),
        width="stretch",
    )

    st.caption(
        "⚠️ Los umbrales de magnitud_categoria usan escala Richter genérica, no la norma "
        "sismorresistente peruana E.030. El z-score aquí se recalcula sobre los datos "
        "filtrados, no representa una medida normativa de riesgo estructural."
    )
