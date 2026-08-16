"""
dashboard/data_loader.py
Carga los parquets de gold y prepara columnas auxiliares para los filtros
del dashboard (semana ISO). El z-score se recalcula dinámicamente después
de filtrar - ver recalcular_zscore() - para que siempre sea coherente con
el subconjunto de datos que el usuario está viendo (no el z-score fijo
calculado una sola vez sobre todo el histórico).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Permite importar config.py aunque streamlit se lance desde dashboard/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import GOLD_PATH, GOLD_DIR  # noqa: E402

AGREGACIONES_PATH = GOLD_DIR / "sismos_agregaciones_departamento_anio.parquet"

MESES_NOMBRE = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


@st.cache_data(show_spinner="Cargando datos de sismos...")
def cargar_gold() -> pd.DataFrame:
    """Carga el detalle de gold y agrega la columna 'semana' (ISO) que no viene persistida."""
    if not GOLD_PATH.exists():
        return pd.DataFrame()

    df = pd.read_parquet(GOLD_PATH)
    df["semana"] = df["fecha_hora_utc"].dt.isocalendar().week.astype(int)
    df["mes_nombre"] = df["mes"].map(MESES_NOMBRE)
    return df


@st.cache_data(show_spinner=False)
def cargar_agregaciones() -> pd.DataFrame:
    if not AGREGACIONES_PATH.exists():
        return pd.DataFrame()
    return pd.read_parquet(AGREGACIONES_PATH)


def recalcular_zscore(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recalcula magnitud_zscore_departamento SOBRE EL SUBCONJUNTO FILTRADO,
    no usa el valor fijo que ya viene en gold. Así, si el usuario filtra
    por año, mes, hora, etc., el z-score sigue siendo coherente con lo que
    está viendo, en vez de comparar contra el historial completo sin filtrar.
    """
    df = df.copy()

    def _zscore(x: pd.Series) -> pd.Series:
        std = x.std()
        if std == 0 or pd.isna(std) or len(x) < 2:
            return pd.Series(0.0, index=x.index)
        return (x - x.mean()) / std

    df["magnitud_zscore_departamento"] = (
        df.groupby("departamento", observed=True)["magnitud"].transform(_zscore)
    )
    return df


def opciones_provincia(df: pd.DataFrame, departamentos_sel: list[str]) -> list[str]:
    """Provincias disponibles, acotadas a los departamentos ya seleccionados (cascada)."""
    sub = df[df["departamento"].isin(departamentos_sel)] if departamentos_sel else df
    return sorted(sub["provincia"].dropna().unique().tolist())


def opciones_distrito(df: pd.DataFrame, departamentos_sel: list[str], provincias_sel: list[str]) -> list[str]:
    """Distritos disponibles, acotados a provincia (o departamento si no hay provincia elegida)."""
    sub = df
    if provincias_sel:
        sub = sub[sub["provincia"].isin(provincias_sel)]
    elif departamentos_sel:
        sub = sub[sub["departamento"].isin(departamentos_sel)]
    return sorted(sub["distrito"].dropna().unique().tolist())


def aplicar_filtros(
    df: pd.DataFrame,
    paises: list[str],
    departamentos: list[str],
    provincias: list[str],
    distritos: list[str],
    anios: list[int],
    meses: list[int],
    semanas: list[int],
    horas: list[int],
    mag_types: list[str],
    magnitud_minima: float,
    tipos_epicentro: list[str],
) -> pd.DataFrame:
    """
    Aplica todos los filtros de la barra lateral en secuencia.
    Lista vacía en cualquier filtro = sin filtrar esa dimensión (se muestra todo),
    no "excluir todo" - mismo patrón en las 10 dimensiones categóricas.
    magnitud_minima es un umbral numérico (>=), no una lista.
    """
    filtrado = df.copy()

    if paises:
        filtrado = filtrado[filtrado["pais"].isin(paises)]
    if departamentos:
        filtrado = filtrado[filtrado["departamento"].isin(departamentos)]
    if provincias:
        filtrado = filtrado[filtrado["provincia"].isin(provincias)]
    if distritos:
        filtrado = filtrado[filtrado["distrito"].isin(distritos)]
    if anios:
        filtrado = filtrado[filtrado["anio"].isin(anios)]
    if meses:
        filtrado = filtrado[filtrado["mes"].isin(meses)]
    if semanas:
        filtrado = filtrado[filtrado["semana"].isin(semanas)]
    if horas:
        filtrado = filtrado[filtrado["hora"].isin(horas)]
    if mag_types:
        filtrado = filtrado[filtrado["mag_type"].isin(mag_types)]
    if tipos_epicentro:
        filtrado = filtrado[filtrado["tipo_epicentro"].isin(tipos_epicentro)]

    filtrado = filtrado[filtrado["magnitud"] >= magnitud_minima]

    return filtrado
