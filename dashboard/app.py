"""
dashboard/app.py
Dashboard interactivo de sismos en Perú (arquitectura medallón - capa gold).
Orquestador delgado: carga datos, arma la sidebar, muestra KPIs y despacha
cada pestaña a su propio módulo en tabs/.

Uso:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import streamlit as st

from data_loader import cargar_gold, aplicar_filtros, recalcular_zscore
from etl_runner import ejecutar_etl_y_recargar
from sidebar import render_sidebar
from resumen import render_resumen
from tabs import ranking, detalle, evolucion, mapa, frecuencia, zscore

st.set_page_config(
    page_title="Sismos Perú",
    page_icon="🌎",
    layout="wide",
)

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
filtros = render_sidebar(df_gold)

# --------------------------------------------------------------------
# Aplicar filtros + recalcular z-score sobre el subconjunto filtrado
# --------------------------------------------------------------------
df_filtrado = aplicar_filtros(
    df_gold, filtros.paises, filtros.departamentos, filtros.provincias, filtros.distritos,
    filtros.anios, filtros.meses, filtros.semanas, filtros.horas, filtros.mag_types,
    filtros.magnitud_minima, filtros.tipos_epicentro,
)
df_filtrado = recalcular_zscore(df_filtrado)

st.title("Sismos en Perú")
st.caption(
    f"Fuente: USGS · magnitud ≥ 4.5 · {len(df_filtrado):,} sismos en la selección actual "
    f"(de {len(df_gold):,} totales)"
)

if df_filtrado.empty:
    st.warning("No hay sismos que coincidan con los filtros seleccionados.")
    st.stop()

# --------------------------------------------------------------------
# KPIs + avisos
# --------------------------------------------------------------------
render_resumen(df_filtrado)

# --------------------------------------------------------------------
# Tabs
# --------------------------------------------------------------------
tab_ranking, tab_detalle, tab_evolucion, tab_mapa, tab_frecuencia, tab_zscore = st.tabs(
    ["🏆 Ranking", "📋 Detalle / Tabla", "📈 Evolución temporal", "🗺️ Mapa", "📊 Magnitud/Frecuencia", "⚡ Z-score / Atípicos"]
)

with tab_ranking:
    ranking.render(df_filtrado, filtros.departamentos, filtros.provincias)

with tab_detalle:
    detalle.render(df_filtrado)

with tab_evolucion:
    evolucion.render(df_filtrado)

with tab_mapa:
    mapa.render(df_filtrado)

with tab_frecuencia:
    frecuencia.render(df_filtrado)

with tab_zscore:
    zscore.render(df_filtrado)
