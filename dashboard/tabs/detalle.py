"""
dashboard/tabs/detalle.py
Pestaña Detalle/Tabla: cada sismo individual (no promedios), ordenable,
descargable a CSV.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from constants import COLOR_MAGNITUD

COLUMNAS_TABLA = [
    "id", "fecha_hora_utc", "pais", "departamento", "provincia", "distrito",
    "tipo_epicentro", "distancia_costa_km",
    "magnitud", "magnitud_categoria", "mag_type", "profundidad_km",
    "profundidad_categoria", "magnitud_zscore_departamento", "lugar",
]


def render(df_filtrado) -> None:
    st.subheader("Todos los sismos en la selección actual")
    st.caption(
        "Vista de detalle (no promedios): cada fila es un sismo individual. "
        "Usa el filtro de 'Magnitud mínima' en la barra lateral para ver, por "
        "ejemplo, solo los sismos de magnitud 6.0 o mayor."
    )


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

    orden_por = st.radio(
        "Ordenar por", ["Magnitud (mayor primero)", "Fecha (más reciente primero)"],
        horizontal=True,
    )
    if orden_por == "Magnitud (mayor primero)":
        df_tabla = df_filtrado.sort_values("magnitud", ascending=False)
    else:
        df_tabla = df_filtrado.sort_values("fecha_hora_utc", ascending=False)
        
    st.write(f"**{len(df_tabla):,}** sismos en la tabla.")

    st.dataframe(
        df_tabla[COLUMNAS_TABLA],
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
        data=df_tabla[COLUMNAS_TABLA].to_csv(index=False).encode("utf-8"),
        file_name="sismos_filtrados.csv",
        mime="text/csv",
    )
