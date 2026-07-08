#!/usr/bin/env python3
"""
Análise de Recorrência de Queimadas na Região Metropolitana de Campinas (RMC)
Utiliza dados de focos de queimadas anuais do INPE (1998-2025)
"""

import os
import zipfile
import requests
import geopandas as gpd
import pandas as pd
import numpy as np
from pathlib import Path
from shapely.geometry import Point
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.cm import ScalarMappable
import warnings
warnings.filterwarnings('ignore')

# Configurações
BASE_URL = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/anual/Brasil_todos_sats"
ANOS = range(1998, 2026)
GEOJSON_PATH = "RMC_Municipios_2024.geojson"
DATA_DIR = Path("dados_queimadas")
OUTPUT_DIR = Path("resultados")

# Criar diretórios
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


def download_and_extract(ano: int, bbox: tuple = None) -> pd.DataFrame:
    """Baixa e extrai o CSV de focos de queimadas para o ano especificado.
    
    Se bbox for fornecido (min_lon, max_lon, min_lat, max_lat),
    filtra apenas os registros dentro do bounding box para reduzir uso de memória.
    """
    filename = f"focos_br_todos-sats_{ano}.zip"
    url = f"{BASE_URL}/{filename}"
    zip_path = DATA_DIR / filename
    csv_path = DATA_DIR / f"focos_br_todos-sats_{ano}.csv"

    if not csv_path.exists() and not zip_path.exists():
        print(f"  Baixando dados de {ano}...")
        try:
            response = requests.get(url, timeout=300)
            response.raise_for_status()
            with open(zip_path, 'wb') as f:
                f.write(response.content)
        except Exception as e:
            print(f"  ERRO ao baixar {ano}: {e}")
            return pd.DataFrame()

    if not csv_path.exists():
        print(f"  Extraindo dados de {ano}...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(DATA_DIR)
            # Buscar CSV recursivamente (pode estar em subdiretórios como tmp/)
            csv_files = list(DATA_DIR.rglob(f"*{ano}*.csv"))
            if csv_files:
                csv_files[0].rename(csv_path)
        except Exception as e:
            print(f"  ERRO ao extrair {ano}: {e}")
            return pd.DataFrame()

    print(f"  Carregando CSV de {ano}...")
    df = pd.read_csv(csv_path, encoding='latin-1', low_memory=False)

    if bbox and not df.empty:
        min_lon, max_lon, min_lat, max_lat = bbox
        df = df[
            (df['longitude'] >= min_lon) & (df['longitude'] <= max_lon) &
            (df['latitude'] >= min_lat) & (df['latitude'] <= max_lat)
        ]
        print(f"  Focos na RMC (pré-filtro bbox): {len(df)}")

    return df


def load_rmc_boundary() -> gpd.GeoDataFrame:
    """Carrega o limites da Região Metropolitana de Campinas."""
    print(f"\nCarregando limites da RMC de {GEOJSON_PATH}...")
    gdf = gpd.read_file(GEOJSON_PATH)
    print(f"  Municípios encontrados: {len(gdf)}")
    print(f"  Municípios: {', '.join(gdf['NM_MUN'].tolist())}")
    return gdf


def filter_focks_in_rmc(df_focos: pd.DataFrame, rmc_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Filtra focos de queimadas que estão dentro da RMC."""
    if df_focos.empty:
        return gpd.GeoDataFrame()

    # Converter para GeoDataFrame
    geometry = [Point(lon, lat) for lon, lat in zip(df_focos['longitude'], df_focos['latitude'])]
    gdf_focos = gpd.GeoDataFrame(df_focos, geometry=geometry, crs="EPSG:4326")

    # Garantir que o CRS do boundary está correto
    if rmc_boundary.crs is None:
        rmc_boundary = rmc_boundary.set_crs("EPSG:4674")
    elif rmc_boundary.crs != gdf_focos.crs:
        rmc_boundary = rmc_boundary.to_crs(gdf_focos.crs)

    # Filtrar focos dentro da RMC
    mask = gpd.sjoin(gdf_focos, rmc_boundary, how='inner', predicate='within')
    return mask


def analyze_frequency(gdf_focos_rmc: gpd.GeoDataFrame) -> pd.DataFrame:
    """Analisa a frequência de queimadas por localização."""
    if gdf_focos_rmc.empty:
        return pd.DataFrame()

    # Agrupar por município e contar focos
    if 'NM_MUN' in gdf_focos_rmc.columns:
        freq_municipio = gdf_focos_rmc.groupby('NM_MUN').size().reset_index(name='total_focos')
        freq_municipio = freq_municipio.sort_values('total_focos', ascending=False)
    else:
        freq_municipio = pd.DataFrame()

    # Criar grade para análise espacial (0.01 grau ≈ 1km)
    gdf_focos_rmc['lat_grid'] = np.round(gdf_focos_rmc['latitude'], 2)
    gdf_focos_rmc['lon_grid'] = np.round(gdf_focos_rmc['longitude'], 2)
    freq_grid = gdf_focos_rmc.groupby(['lat_grid', 'lon_grid']).size().reset_index(name='total_focos')
    freq_grid = freq_grid.sort_values('total_focos', ascending=False)

    return freq_municipio, freq_grid


def create_visualizations(gdf_focos_rmc: gpd.GeoDataFrame, rmc_boundary: gpd.GeoDataFrame,
                          freq_municipio: pd.DataFrame, freq_grid: pd.DataFrame):
    """Cria visualizações dos resultados."""

    # 1. Mapa de calor dos focos
    fig, axes = plt.subplots(2, 2, figsize=(20, 16))

    # Mapa 1: Todos os focos
    ax1 = axes[0, 0]
    rmc_boundary.plot(ax=ax1, color='lightgray', edgecolor='black', linewidth=0.5)
    if not gdf_focos_rmc.empty:
        gdf_focos_rmc.plot(ax=ax1, markersize=1, alpha=0.3, color='red', zorder=5)
    ax1.set_title('Focos de Queimadas na RMC (1998-2025)', fontsize=14, fontweight='bold')
    ax1.set_xlabel('Longitude')
    ax1.set_ylabel('Latitude')

    # Mapa 2: Densidade de focos (heatmap)
    ax2 = axes[0, 1]
    rmc_boundary.plot(ax=ax2, color='lightgray', edgecolor='black', linewidth=0.5)
    if not freq_grid.empty:
        scatter = ax2.scatter(freq_grid['lon_grid'], freq_grid['lat_grid'],
                            c=freq_grid['total_focos'], cmap='YlOrRd',
                            s=freq_grid['total_focos'] / freq_grid['total_focos'].max() * 100,
                            alpha=0.7, edgecolors='black', linewidth=0.5)
        plt.colorbar(scatter, ax=ax2, label='Número de Focos')
    ax2.set_title('Densidade de Focos de Queimadas', fontsize=14, fontweight='bold')
    ax2.set_xlabel('Longitude')
    ax2.set_ylabel('Latitude')

    # Mapa 3: Focos por município (barras)
    ax3 = axes[1, 0]
    if not freq_municipio.empty:
        top_20 = freq_municipio.head(20)
        bars = ax3.barh(top_20['NM_MUN'], top_20['total_focos'], color='orangered', edgecolor='black')
        ax3.set_xlabel('Número de Focos')
        ax3.set_title('Top 20 Municípios com Mais Focos', fontsize=14, fontweight='bold')
        ax3.invert_yaxis()

    # Mapa 4: Evolução temporal
    ax4 = axes[1, 1]
    if not gdf_focos_rmc.empty and 'ano' in gdf_focos_rmc.columns:
        evolucao = gdf_focos_rmc.groupby('ano').size()
        ax4.plot(evolucao.index, evolucao.values, marker='o', linewidth=2, markersize=6, color='darkred')
        ax4.fill_between(evolucao.index, evolucao.values, alpha=0.3, color='red')
        ax4.set_xlabel('Ano')
        ax4.set_ylabel('Número de Focos')
        ax4.set_title('Evolução Temporal dos Focos (1998-2025)', fontsize=14, fontweight='bold')
        ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'analise_queimadas_rmc.png', dpi=300, bbox_inches='tight')
    plt.close()

    # Mapa interativo com focos quentes
    fig2, ax = plt.subplots(figsize=(15, 12))
    rmc_boundary.plot(ax=ax, color='lightgray', edgecolor='black', linewidth=0.8)

    if not freq_grid.empty:
        # Normalizar para cores
        norm = mcolors.Normalize(vmin=freq_grid['total_focos'].min(),
                                vmax=freq_grid['total_focos'].max())
        cmap = plt.cm.YlOrRd

        scatter = ax.scatter(freq_grid['lon_grid'], freq_grid['lat_grid'],
                           c=freq_grid['total_focos'], cmap=cmap, norm=norm,
                           s=freq_grid['total_focos'] * 2, alpha=0.8,
                           edgecolors='black', linewidth=0.5, zorder=5)

        cbar = plt.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax, label='Número de Focos')

    # Adicionar nomes dos municípios
    for idx, row in rmc_boundary.iterrows():
        centroid = row.geometry.centroid
        ax.annotate(row['NM_MUN'], xy=(centroid.x, centroid.y),
                   ha='center', va='center', fontsize=7, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7))

    ax.set_title('Mapa de Recorrência de Queimadas na RMC (1998-2025)\nTamanho e cor indicam frequência',
                fontsize=16, fontweight='bold')
    ax.set_xlabel('Longitude', fontsize=12)
    ax.set_ylabel('Latitude', fontsize=12)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'mapa_recorrencia_rmc.png', dpi=300, bbox_inches='tight')
    plt.close()


def save_results(freq_municipio: pd.DataFrame, freq_grid: pd.DataFrame, gdf_focos_rmc: gpd.GeoDataFrame):
    """Salva os resultados em arquivos CSV."""
    if not freq_municipio.empty:
        freq_municipio.to_csv(OUTPUT_DIR / 'focos_por_municipio.csv', index=False, encoding='utf-8')
        print(f"\nResultados salvos em {OUTPUT_DIR / 'focos_por_municipio.csv'}")

    if not freq_grid.empty:
        freq_grid.to_csv(OUTPUT_DIR / 'focos_por_grid.csv', index=False, encoding='utf-8')
        print(f"Resultados salvos em {OUTPUT_DIR / 'focos_por_grid.csv'}")

    if not gdf_focos_rmc.empty:
        gdf_focos_rmc.to_csv(OUTPUT_DIR / 'todos_focos_rmc.csv', index=False, encoding='utf-8')
        print(f"Resultados salvos em {OUTPUT_DIR / 'todos_focos_rmc.csv'}")


def main():
    print("=" * 70)
    print("ANÁLISE DE RECORRÊNCIA DE QUEIMADAS NA REGIÃO METROPOLITANA DE CAMPINAS")
    print("Dados: INPE - Focos de Queimadas Anuais (1998-2025)")
    print("=" * 70)

    # Carregar limites da RMC
    rmc_boundary = load_rmc_boundary()

    # Calcular bounding box da RMC para pré-filtro (reduz memória drasticamente)
    min_lon, min_lat, max_lon, max_lat = rmc_boundary.total_bounds
    bbox = (min_lon, max_lon, min_lat, max_lat)
    print(f"  Bounding box RMC: lon [{min_lon:.4f}, {max_lon:.4f}], lat [{min_lat:.4f}, {max_lat:.4f}]")

    # Lista para armazenar focos já filtrados para a RMC
    all_focos_rmc = []

    # Download e processamento de cada ano — filtra imediatamente pelo bbox
    print("\nBaixando e processando dados de focos de queimadas...")
    for ano in ANOS:
        print(f"\nProcessando ano {ano}:")
        df = download_and_extract(ano, bbox=bbox)
        if not df.empty:
            if 'ano' not in df.columns:
                df['ano'] = ano
            all_focos_rmc.append(df)
            print(f"  Focos na RMC após pré-filtro: {len(df)}")

    if not all_focos_rmc:
        print("\nERRO: Nenhum dado foi carregado. Verifique a conexão com a internet.")
        return

    # Combinar apenas os dados já filtrados para a RMC
    print("\nCombinando dados da RMC de todos os anos...")
    df_total = pd.concat(all_focos_rmc, ignore_index=True)
    del all_focos_rmc
    print(f"Total de focos na RMC (pré-filtro): {len(df_total)}")

    # Verificar colunas disponíveis
    print(f"\nColunas disponíveis: {list(df_total.columns)}")

    # Filtrar focos dentro da RMC usando join geoespacial (precisão total)
    print("\nFiltrando focos dentro da Região Metropolitana de Campinas (join espacial)...")
    gdf_focos_rmc = filter_focks_in_rmc(df_total, rmc_boundary)
    print(f"Total de focos na RMC: {len(gdf_focos_rmc)}")

    if gdf_focos_rmc.empty:
        print("\nNenhum foco encontrado dentro da RMC. Verifique os dados.")
        return

    # Análise de frequência
    print("\nCalculando frequência de queimadas...")
    freq_municipio, freq_grid = analyze_frequency(gdf_focos_rmc)

    # Exibir resultados
    print("\n" + "=" * 70)
    print("RESULTADOS - TOP 10 MUNICÍPIOS COM MAIS FOCOS DE QUEIMADAS")
    print("=" * 70)
    if not freq_municipio.empty:
        print(freq_municipio.head(10).to_string(index=False))

    print("\n" + "=" * 70)
    print("TOP 10 LOCAIS COM MAIS RECORRÊNCIA (GRADE 1km x 1km)")
    print("=" * 70)
    if not freq_grid.empty:
        print(freq_grid.head(10).to_string(index=False))

    # Criar visualizações
    print("\nGerando visualizações...")
    create_visualizations(gdf_focos_rmc, rmc_boundary, freq_municipio, freq_grid)

    # Salvar resultados
    save_results(freq_municipio, freq_grid, gdf_focos_rmc)

    print("\n" + "=" * 70)
    print("ANÁLISE CONCLUÍDA!")
    print(f"Arquivos gerados em: {OUTPUT_DIR.absolute()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
