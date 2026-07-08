#!/usr/bin/env python3
"""
App Streamlit — Mapas de Recorrência de Queimadas na RMC
Exibe os 10 mapas gerados pelo script R com estatísticas interativas.
"""

import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(
    page_title="Queimadas RMC — Análise de Recorrência",
    page_icon="🔥",
    layout="wide",
)

RESULTADOS = Path("resultados")

# --- Dados brutos (se existirem) --------------------------------------------
@st.cache_data
def load_data():
    csv = RESULTADOS / "todos_focos_rmc.csv"
    if csv.exists():
        return pd.read_csv(csv, parse_dates=["data_pas"])
    return None

df = load_data()

# --- Sidebar ----------------------------------------------------------------
st.sidebar.title("🔥 Queimadas RMC")
st.sidebar.markdown("Região Metropolitana de Campinas — Dados INPE (1998‑2025)")

if df is not None:
    st.sidebar.metric("Total de focos", f"{len(df):,}")
    st.sidebar.metric("Anos analisados", f"{df['ano'].min()}–{df['ano'].max()}")
    st.sidebar.metric("Municípios", df["NM_MUN"].nunique())
    mes_mais = df["mes"].mode().iloc[0] if "mes" in df.columns else "—"
    st.sidebar.metric("Mês mais crítico", str(mes_mais))

    st.sidebar.divider()
    ano_min, ano_max = int(df["ano"].min()), int(df["ano"].max())
    anos = st.sidebar.slider(
        "Filtrar por ano",
        min_value=ano_min, max_value=ano_max,
        value=(ano_min, ano_max),
    )
    municipios = st.sidebar.multiselect(
        "Filtrar por município",
        sorted(df["NM_MUN"].unique()),
    )
else:
    anos = None
    municipios = []

# --- Mapas disponíveis -------------------------------------------------------
MAPAS = [
    ("mapa_01_todos_focos.png",           "📍 Todos os Focos",
     "Dispersão de todos os focos de queimadas com escala de FRP (Fire Radiative Power)."),
    ("mapa_02_recorrencia_grade.png",     "🔁 Recorrência (Grade 1km)",
     "Densidade de focos por grade de 1km × 1km — tamanho e cor indicam frequência."),
    ("mapa_03_focos_por_municipio.png",   "🏘️ Focos por Município",
     "Mapa coroplético com total de focos por município (escala logarítmica)."),
    ("mapa_04_evolucao_decada.png",       "📅 Evolução por Década",
     "Distribuição espacial dos focos por década (1998‑2005, 2006‑2015, 2016‑2025)."),
    ("mapa_05_distribuicao_mensal.png",   "📊 Distribuição Mensal",
     "Quantidade de focos por mês ao longo de todo o período."),
    ("mapa_06_top20_municipios.png",      "🏆 Top 20 Municípios",
     "Os 20 municípios com maior número absoluto de focos de queimadas."),
    ("mapa_07_evolucao_temporal.png",     "📈 Evolução Temporal",
     "Série temporal dos focos de queimadas de 1998 a 2025."),
    ("mapa_08_heatmap_ano_mes.png",       "🌡️ Heatmap Ano × Mês",
     "Mapa de calor mostrando a intensidade de focos por ano e mês."),
    ("mapa_09_frp_medio_municipio.png",   "🔥 FRP Médio por Município",
     "Intensidade média dos focos (Fire Radiative Power) por município."),
    ("mapa_10_continuidade_temporal.png", "⏱️ Continuidade Temporal",
     "Número de anos (de 28) em que cada município registrou pelo menos 1 foco."),
]

# --- Título ------------------------------------------------------------------
st.title("🔥 Mapas de Recorrência de Queimadas — RMC")
st.caption("Região Metropolitana de Campinas · Dados INPE · 1998–2025")

# --- Abas --------------------------------------------------------------------
tab_maps, tab_data, tab_about = st.tabs(["🗺️ Mapas", "📋 Dados", "ℹ️ Sobre"])

# ---------------------------------------------------------------------------
with tab_maps:
    for fname, titulo, desc in MAPAS:
        fpath = RESULTADOS / fname
        if not fpath.exists():
            continue
        with st.expander(titulo, expanded=fname == "mapa_01_todos_focos.png"):
            st.markdown(f"**{desc}**")
            st.image(str(fpath), use_container_width=True)

# ---------------------------------------------------------------------------
with tab_data:
    if df is not None:
        st.subheader("Dados brutos dos focos de queimadas")

        filtered = df.copy()
        if anos:
            filtered = filtered[(filtered["ano"] >= anos[0]) & (filtered["ano"] <= anos[1])]
        if municipios:
            filtered = filtered[filtered["NM_MUN"].isin(municipios)]

        st.metric("Registros filtrados", f"{len(filtered):,}")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Focos por município")
            freq = (filtered.groupby("NM_MUN").size()
                    .reset_index(name="total_focos")
                    .sort_values("total_focos", ascending=False))
            st.dataframe(freq, use_container_width=True, height=400)

        with col2:
            st.subheader("Focos por ano")
            ano_freq = (filtered.groupby("ano").size()
                        .reset_index(name="total_focos")
                        .sort_values("ano"))
            st.bar_chart(ano_freq.set_index("ano"))

        st.subheader("Amostra dos dados")
        display_cols = ["latitude", "longitude", "data_pas", "satelite",
                        "municipio", "bioma", "frp", "ano"]
        existing = [c for c in display_cols if c in filtered.columns]
        st.dataframe(filtered[existing].head(200), use_container_width=True, height=350)
    else:
        st.info("Arquivo `todos_focos_rmc.csv` não encontrado em `resultados/`.")

# ---------------------------------------------------------------------------
with tab_about:
    st.markdown("""
## Sobre este painel

Este painel interativo apresenta a **análise de recorrência de queimadas**
na **Região Metropolitana de Campinas (RMC)**, Estado de São Paulo, Brasil.

**Fonte dos dados:**
[INPE — Programa Queimadas](https://queimadas.dgi.inpe.br/)
— Focos de queimadas anuais via satélite (1998–2025).

**Municípios da RMC (20):**
Campinas, Americana, Artur Nogueira, Cosmópolis, Engenheiro Coelho,
Hortolândia, Holambra, Indaiatuba, Itatiba, Jaguariúna, Monte Mor,
Nova Odessa, Paulínia, Pedreira, Santa Bárbara d'Oeste,
Santo Antônio de Posse, Sumaré, Valinhos, Vinhedo, Morungaba.

**Ferramentas:**
- Python + Streamlit (este app)
- R + sf + ggplot2 (geração dos mapas)
- Dados INPE (focos por satélite)
    """)

# --- Rodapé -----------------------------------------------------------------
st.divider()
st.caption("Gerado automaticamente · Dados INPE · Análise de Recorrência de Queimadas na RMC")
