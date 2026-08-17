"""
dashboard/tabs/ranking.py
Pestaña Ranking: sismos por departamento/provincia/distrito, con
drill-down jerárquico automático según lo elegido en el sidebar.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from constants import COLOR_MAGNITUD


def render(df_filtrado, deptos_sel: list, provincias_sel: list) -> None:
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
