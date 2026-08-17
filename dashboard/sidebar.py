"""
dashboard/sidebar.py
Renderiza toda la barra lateral (botón de actualizar + los 11 filtros) y
devuelve las selecciones empaquetadas en un dataclass Filtros, para no
tener que pasar 11 parámetros sueltos entre módulos.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from data_loader import opciones_provincia, opciones_distrito, MESES_NOMBRE
from etl_runner import ejecutar_etl_y_recargar


@dataclass
class Filtros:
    paises: list
    departamentos: list
    provincias: list
    distritos: list
    anios: list
    meses: list
    semanas: list
    horas: list
    mag_types: list
    magnitud_minima: float
    tipos_epicentro: list


def render_sidebar(df_gold) -> Filtros:
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

    return Filtros(
        paises=paises_sel,
        departamentos=deptos_sel,
        provincias=provincias_sel,
        distritos=distritos_sel,
        anios=anios_sel,
        meses=meses_sel,
        semanas=semanas_sel,
        horas=horas_sel,
        mag_types=magtype_sel,
        magnitud_minima=magnitud_minima,
        tipos_epicentro=tipo_epicentro_sel,
    )
