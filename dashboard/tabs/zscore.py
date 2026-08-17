"""
dashboard/tabs/zscore.py
Pestaña Z-score / Atípicos: sismos inusuales respecto al historial de su
propio departamento.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st


def render(df_filtrado) -> None:
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
