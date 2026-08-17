"""
dashboard/etl_runner.py
Corre etl.py (bronze -> silver -> gold) desde un botón del dashboard,
sin salir a una terminal.
"""

from __future__ import annotations

import subprocess
import sys

import streamlit as st

from config import BASE_DIR
from data_loader import cargar_gold, cargar_agregaciones


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
