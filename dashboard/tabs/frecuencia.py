"""
dashboard/tabs/frecuencia.py
Pestaña Magnitud/Frecuencia: distribución de magnitud (Gutenberg-Richter),
distribución por tipo de magnitud, y diccionario de tipos de magnitud.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st


def render(df_filtrado) -> None:
    st.subheader("Distribución de magnitud")
    fig = px.histogram(
        df_filtrado, x="magnitud", nbins=30, text_auto=True,
        labels={"magnitud": "Magnitud", "count": "Cantidad de sismos"},
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "A mayor magnitud, menor frecuencia - patrón esperado (Ley de Gutenberg-Richter). "
        "Nota: sin declustering de réplicas, un sismo grande con muchas réplicas puede "
        "inflar el conteo de magnitudes bajas en su misma zona/período."
    )

    st.subheader("Distribución por tipo de magnitud (mag_type)")
    fig2 = px.histogram(df_filtrado, x="magnitud", color="mag_type", nbins=30, barmode="overlay", opacity=0.6)
    st.plotly_chart(fig2, width="stretch")
    st.caption(
        "mb tiende a subestimar sismos grandes (>6.5) frente a mww/mwc. "
        "Ten esto en cuenta al comparar magnitudes entre eventos de distinto mag_type."
    )

    with st.expander("📖 ¿Qué significa cada tipo de magnitud?"):
        st.markdown(
            """
| Código | Nombre | Qué mide |
|---|---|---|
| `mb` | Magnitud de ondas de cuerpo | Amplitud de las ondas P; común en reportes rápidos/automáticos. Subestima sismos grandes (>6.5) |
| `ml` | Magnitud local (Richter) | La escala clásica de Richter (1935); amplitud cerca del epicentro |
| `ms` | Magnitud de ondas superficiales | Amplitud de ondas superficiales; usada históricamente para sismos moderados-grandes |
| `md` | Magnitud de duración (coda) | Duración de la señal sísmica registrada; común en sismos pequeños |
| `mww` | Momento sísmico, método W-phase | Estándar de USGS para sismos M5.0+ (confiable desde M5.5). No se satura en sismos grandes |
| `mwc` | Momento sísmico, método centroide (CMT) | Similar a `mww`, calculado con tensor de momento centroide |
| `mwb` | Momento sísmico, ondas P de banda ancha | Estimación de momento sísmico a partir de ondas P de banda ancha |
| `mwr` | Momento sísmico, distancia regional | Estimación de momento sísmico con redes sismológicas regionales |
| `m` | Magnitud genérica | Método de cálculo no especificado en el catálogo de origen |

`mww`, `mwc`, `mwb` y `mwr` son todas variantes del **momento sísmico (Mw)** - miden
la energía física liberada directamente, a diferencia de `mb`/`ml`/`ms` que miden
amplitud de onda y pueden "saturarse" (dejar de crecer) en sismos muy grandes.
"""
        )
