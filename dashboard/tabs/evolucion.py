"""
dashboard/tabs/evolucion.py
Pestaña Evolución temporal: magnitud promedio por año, cantidad de sismos
por año segmentada por departamento (con total siempre visible), magnitud
promedio por hora del día, y tabla resumen de todos los departamentos.
"""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def render(df_filtrado) -> None:
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
