"""
dashboard/resumen.py
KPIs principales + avisos sobre la selección actual (sismos offshore,
sismos sin zona asignada).
"""

from __future__ import annotations

import streamlit as st


def render_resumen(df_filtrado) -> None:
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
