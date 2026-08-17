"""
dashboard/tabs/mapa.py
Pestaña Mapa: ubicación geográfica interactiva de los sismos, con
diccionario de umbrales de magnitud y su efecto estimado.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from constants import COLOR_MAGNITUD


def render(df_filtrado) -> None:
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
