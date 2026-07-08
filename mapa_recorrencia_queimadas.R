#!/usr/bin/env Rscript
# =============================================================================
# Mapa Detalhado de Recorrência de Queimadas na RMC (Região Metropolitana de Campinas)
# Lê dados de focos de queimadas e cria visualizações espaciais detalhadas
# =============================================================================

# --- Carregar pacotes -------------------------------------------------------
required_packages <- c("sf", "ggplot2", "dplyr", "tidyr", "viridis",
                       "scales", "lubridate")

for (pkg in required_packages) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    install.packages(pkg, repos = "https://cran.r-project.org")
  }
  library(pkg, character.only = TRUE)
}

# --- Configurações ----------------------------------------------------------
data_file   <- "resultados/todos_focos_rmc.csv"
geojson_file <- "RMC_Municipios_2024.geojson"
output_dir  <- "resultados"

cat("============================================================\n")
cat("MAPA DETALHADO DE RECORRÊNCIA DE QUEIMADAS NA RMC\n")
cat("============================================================\n\n")

# --- 1. Ler dados -----------------------------------------------------------
cat("Lendo dados de focos de queimadas...\n")
focos <- read.csv(data_file, stringsAsFactors = FALSE, encoding = "UTF-8")

cat(sprintf("  Total de registros: %d\n", nrow(focos)))
cat(sprintf("  Período: %d - %d\n", min(focos$ano), max(focos$ano)))

# Converter data_pas para formato de data
focos$data_pas <- as.POSIXct(focos$data_pas, format = "%Y-%m-%d %H:%M:%S")
focos$mes <- month(focos$data_pas, label = TRUE, abbr = FALSE)
focos$dia_juliano <- yday(focos$data_pas)

# --- 2. Carregar limites da RMC (GeoJSON) -----------------------------------
cat("Carregando limites municipais da RMC...\n")
rmc_sf <- st_read(geojson_file, quiet = TRUE)
cat(sprintf("  Municípios: %d\n", nrow(rmc_sf)))

# --- 3. Converter focos para sf ----------------------------------------------
cat("Convertendo focos para objeto espacial...\n")
focos_sf <- st_as_sf(focos, coords = c("longitude", "latitude"), crs = 4326)

# --- 4. Análise por município ------------------------------------------------
cat("Calculando estatísticas por município...\n")
freq_municipio <- focos %>%
  group_by(NM_MUN) %>%
  summarise(
    total_focos    = n(),
    media_frp      = mean(frp, na.rm = TRUE),
    max_frp        = max(frp, na.rm = TRUE),
    anos_presentes = n_distinct(ano),
    focos_por_ano  = total_focos / anos_presentes,
    .groups = "drop"
  ) %>%
  arrange(desc(total_focos))

cat("\nTop 10 municípios com mais focos:\n")
print(head(freq_municipio, 10), n = 10)

# --- 5. Análise temporal -----------------------------------------------------
cat("\nCalculando evolução temporal...\n")
evolucao_ano <- focos %>%
  group_by(ano) %>%
  summarise(total_focos = n(), .groups = "drop")

evolucao_mes <- focos %>%
  group_by(ano, mes) %>%
  summarise(total_focos = n(), .groups = "drop")

# --- 6. Análise por bioma ----------------------------------------------------
cat("Análise por bioma...\n")
freq_bioma <- focos %>%
  group_by(bioma) %>%
  summarise(total_focos = n(), .groups = "drop") %>%
  arrange(desc(total_focos))

# --- 7. Análise por satélite -------------------------------------------------
cat("Análise por satélite...\n")
freq_sat <- focos %>%
  group_by(satelite) %>%
  summarise(total_focos = n(), .groups = "drop") %>%
  arrange(desc(total_focos))

# --- 8. Grade de recorrência (1km x 1km) ------------------------------------
cat("Criando grade de recorrência...\n")
focos_grid <- focos %>%
  mutate(lat_grid = round(latitude, 2),
         lon_grid = round(longitude, 2)) %>%
  group_by(lat_grid, lon_grid) %>%
  summarise(
    total_focos  = n(),
    anos_unicos  = n_distinct(ano),
    frp_medio    = mean(frp, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  arrange(desc(total_focos))

grid_sf <- st_as_sf(focos_grid, coords = c("lon_grid", "lat_grid"), crs = 4326)

# =============================================================================
# VISUALIZAÇÕES
# =============================================================================

cat("\nGerando visualizações...\n")

# --- Mapa 1: Todos os focos com limites municipais -------------------------
cat("  Mapa 1: Dispersão de todos os focos...\n")
p1 <- ggplot() +
  geom_sf(data = rmc_sf, fill = "grey95", color = "grey40", linewidth = 0.3) +
  geom_sf(data = focos_sf, aes(color = frp), size = 0.4, alpha = 0.5) +
  scale_color_viridis_c(option = "inferno", name = "FRP", na.value = "grey50") +
  geom_sf_text(data = rmc_sf, aes(label = NM_MUN), size = 2.2, fontface = "bold",
               color = "black", nudge_y = 0.008) +
  labs(
    title    = "Focos de Queimadas na Região Metropolitana de Campinas",
    subtitle = "Período: 1998–2025 | Dados: INPE",
    x = "Longitude", y = "Latitude"
  ) +
  theme_minimal(base_size = 11) +
  theme(
    plot.title    = element_text(face = "bold", size = 14),
    plot.subtitle = element_text(color = "grey40"),
    panel.grid.minor = element_blank()
  )

ggsave(file.path(output_dir, "mapa_01_todos_focos.png"), p1,
       width = 12, height = 10, dpi = 300)

# --- Mapa 2: Densidade por grade (recorrência) -----------------------------
cat("  Mapa 2: Densidade / recorrência por grade...\n")
p2 <- ggplot() +
  geom_sf(data = rmc_sf, fill = "grey95", color = "grey40", linewidth = 0.3) +
  geom_sf(data = grid_sf, aes(size = total_focos, color = total_focos), alpha = 0.7) +
  scale_color_viridis_c(option = "plasma", name = "Nº de Focos", trans = "log10") +
  scale_size_continuous(range = c(0.5, 8), guide = "none") +
  geom_sf_text(data = rmc_sf, aes(label = NM_MUN), size = 2.2, fontface = "bold",
               color = "black", nudge_y = 0.008) +
  labs(
    title    = "Mapa de Recorrência de Queimadas (Grade 1km × 1km)",
    subtitle = "Tamanho e cor indicam frequência de focos (1998–2025)",
    x = "Longitude", y = "Latitude"
  ) +
  theme_minimal(base_size = 11) +
  theme(
    plot.title    = element_text(face = "bold", size = 14),
    plot.subtitle = element_text(color = "grey40"),
    panel.grid.minor = element_blank()
  )

ggsave(file.path(output_dir, "mapa_02_recorrencia_grade.png"), p2,
       width = 12, height = 10, dpi = 300)

# --- Mapa 3: Focos por município (coropletico) ------------------------------
cat("  Mapa 3: Focos por município (coroplético)...\n")
rmc_map <- rmc_sf %>%
  left_join(freq_municipio, by = "NM_MUN")

p3 <- ggplot(rmc_map) +
  geom_sf(aes(fill = total_focos), color = "grey30", linewidth = 0.3) +
  scale_fill_viridis_c(option = "magma", name = "Nº de Focos", trans = "log10",
                       na.value = "grey90") +
  geom_sf_text(aes(label = NM_MUN), size = 2.0, fontface = "bold", color = "white") +
  labs(
    title    = "Total de Focos de Queimadas por Município (1998–2025)",
    subtitle = "Escala logarítmica | Dados: INPE",
    x = "Longitude", y = "Latitude"
  ) +
  theme_minimal(base_size = 11) +
  theme(
    plot.title    = element_text(face = "bold", size = 14),
    plot.subtitle = element_text(color = "grey40"),
    panel.grid.minor = element_blank()
  )

ggsave(file.path(output_dir, "mapa_03_focos_por_municipio.png"), p3,
       width = 12, height = 10, dpi = 300)

# --- Mapa 4: Evolução temporal por município (facetas por década) -----------
cat("  Mapa 4: Evolução temporal por década...\n")
focos_decada <- focos %>%
  mutate(decada = cut(ano, breaks = c(1997, 2005, 2015, 2026),
                      labels = c("1998–2005", "2006–2015", "2016–2025"))) %>%
  count(NM_MUN, decada)

rmc_decada <- rmc_sf %>%
  left_join(focos_decada, by = "NM_MUN")

p4 <- ggplot(rmc_decada) +
  geom_sf(aes(fill = n), color = "grey30", linewidth = 0.2) +
  scale_fill_viridis_c(option = "cividis", name = "Nº de Focos", na.value = "grey95") +
  facet_wrap(~ decada, ncol = 3) +
  labs(
    title    = "Evolução Temporal dos Focos por Município e Década",
    subtitle = "Região Metropolitana de Campinas | Dados: INPE",
    x = "Longitude", y = "Latitude"
  ) +
  theme_minimal(base_size = 10) +
  theme(
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(color = "grey40"),
    strip.text       = element_text(face = "bold", size = 11),
    panel.grid.minor = element_blank(),
    legend.position  = "bottom"
  )

ggsave(file.path(output_dir, "mapa_04_evolucao_decada.png"), p4,
       width = 16, height = 7, dpi = 300)

# --- Mapa 5: Meses mais críticos --------------------------------------------
cat("  Mapa 5: Distribuição mensal...\n")
p5 <- ggplot(focos, aes(x = mes, fill = ..count..)) +
  geom_bar(color = "black", linewidth = 0.2) +
  scale_fill_viridis_c(option = "plasma", guide = "none") +
  labs(
    title    = "Distribuição Mensal dos Focos de Queimadas na RMC",
    subtitle = "Período: 1998–2025 | Dados: INPE",
    x = "Mês", y = "Número de Focos"
  ) +
  theme_minimal(base_size = 11) +
  theme(
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(color = "grey40"),
    axis.text.x      = element_text(angle = 45, hjust = 1),
    panel.grid.minor = element_blank()
  )

ggsave(file.path(output_dir, "mapa_05_distribuicao_mensal.png"), p5,
       width = 10, height = 6, dpi = 300)

# --- Mapa 6: Top 20 municípios (barras) -------------------------------------
cat("  Mapa 6: Top 20 municípios...\n")
top20 <- head(freq_municipio, 20)

p6 <- ggplot(top20, aes(x = reorder(NM_MUN, total_focos), y = total_focos)) +
  geom_col(aes(fill = total_focos), color = "black", linewidth = 0.2) +
  scale_fill_viridis_c(option = "inferno", guide = "none") +
  geom_text(aes(label = comma(total_focos)), hjust = -0.1, size = 3) +
  coord_flip() +
  scale_y_continuous(labels = comma, expand = expansion(mult = c(0, 0.15))) +
  labs(
    title    = "Top 20 Municípios com Mais Focos de Queimadas",
    subtitle = "Região Metropolitana de Campinas (1998–2025)",
    x = NULL, y = "Número de Focos"
  ) +
  theme_minimal(base_size = 11) +
  theme(
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(color = "grey40"),
    panel.grid.major.y = element_blank(),
    panel.grid.minor   = element_blank()
  )

ggsave(file.path(output_dir, "mapa_06_top20_municipios.png"), p6,
       width = 10, height = 8, dpi = 300)

# --- Mapa 7: Evolução temporal (linha) --------------------------------------
cat("  Mapa 7: Evolução temporal...\n")
p7 <- ggplot(evolucao_ano, aes(x = ano, y = total_focos)) +
  geom_area(fill = "red", alpha = 0.3) +
  geom_line(color = "darkred", linewidth = 1) +
  geom_point(color = "darkred", size = 2) +
  scale_y_continuous(labels = comma) +
  labs(
    title    = "Evolução Temporal dos Focos de Queimadas na RMC",
    subtitle = "Período: 1998–2025 | Dados: INPE",
    x = "Ano", y = "Número de Focos"
  ) +
  theme_minimal(base_size = 11) +
  theme(
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(color = "grey40"),
    panel.grid.minor = element_blank()
  )

ggsave(file.path(output_dir, "mapa_07_evolucao_temporal.png"), p7,
       width = 12, height = 6, dpi = 300)

# --- Mapa 8: Heatmap ano x mês ---------------------------------------------
cat("  Mapa 8: Heatmap ano × mês...\n")
heatmap_data <- focos %>%
  group_by(ano, mes) %>%
  summarise(total_focos = n(), .groups = "drop")

p8 <- ggplot(heatmap_data, aes(x = mes, y = ano, fill = total_focos)) +
  geom_tile(color = "white", linewidth = 0.1) +
  scale_fill_viridis_c(option = "plasma", name = "Nº de Focos", trans = "log10") +
  labs(
    title    = "Heatmap de Focos de Queimadas — Ano × Mês",
    subtitle = "Região Metropolitana de Campinas (1998–2025)",
    x = "Mês", y = "Ano"
  ) +
  theme_minimal(base_size = 11) +
  theme(
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(color = "grey40"),
    axis.text.x      = element_text(angle = 45, hjust = 1),
    panel.grid.minor = element_blank()
  )

ggsave(file.path(output_dir, "mapa_08_heatmap_ano_mes.png"), p8,
       width = 12, height = 10, dpi = 300)

# --- Mapa 9: FRP médio por município ----------------------------------------
cat("  Mapa 9: Intensidade (FRP) por município...\n")
p9 <- ggplot(rmc_map) +
  geom_sf(aes(fill = media_frp), color = "grey30", linewidth = 0.3) +
  scale_fill_viridis_c(option = "rocket", name = "FRP Médio", na.value = "grey90") +
  geom_sf_text(aes(label = NM_MUN), size = 2.0, fontface = "bold", color = "white") +
  labs(
    title    = "FRP Médio dos Focos por Município",
    subtitle = "Fire Radiative Power — Região Metropolitana de Campinas (1998–2025)",
    x = "Longitude", y = "Latitude"
  ) +
  theme_minimal(base_size = 11) +
  theme(
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(color = "grey40"),
    panel.grid.minor = element_blank()
  )

ggsave(file.path(output_dir, "mapa_09_frp_medio_municipio.png"), p9,
       width = 12, height = 10, dpi = 300)

# --- Mapa 10: Anos de presença por município --------------------------------
cat("  Mapa 10: Continuidade temporal por município...\n")
p10 <- ggplot(rmc_map) +
  geom_sf(aes(fill = anos_presentes), color = "grey30", linewidth = 0.3) +
  scale_fill_viridis_c(option = "viridis", name = "Anos c/ Focos",
                       breaks = seq(0, 28, by = 5), na.value = "grey90") +
  geom_sf_text(aes(label = NM_MUN), size = 2.0, fontface = "bold", color = "white") +
  labs(
    title    = "Continuidade Temporal dos Focos por Município",
    subtitle = "Número de anos (de 28) com pelo menos 1 foco registrado",
    x = "Longitude", y = "Latitude"
  ) +
  theme_minimal(base_size = 11) +
  theme(
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(color = "grey40"),
    panel.grid.minor = element_blank()
  )

ggsave(file.path(output_dir, "mapa_10_continuidade_temporal.png"), p10,
       width = 12, height = 10, dpi = 300)

# =============================================================================
# RESUMO FINAL
# =============================================================================
cat("\n============================================================\n")
cat("ANÁLISE CONCLUÍDA — 10 MAPAS GERADOS\n")
cat("============================================================\n")
cat(sprintf("  Total de focos na RMC: %d\n", nrow(focos)))
cat(sprintf("  Período: %d–%d (%d anos)\n",
            min(focos$ano), max(focos$ano), n_distinct(focos$ano)))
cat(sprintf("  Municípios com focos: %d\n", n_distinct(focos$NM_MUN)))
cat(sprintf("  Mês mais crítico: %s\n",
            levels(focos$mes)[which.max(table(focos$mes))]))
cat(sprintf("  Município com mais focos: %s (%d focos)\n",
            freq_municipio$NM_MUN[1], freq_municipio$total_focos[1]))
cat(sprintf("\nArquivos salvos em: %s/\n", normalizePath(output_dir)))
cat("============================================================\n")
