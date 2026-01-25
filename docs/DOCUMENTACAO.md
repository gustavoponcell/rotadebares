# Documentação viva — Roteirização de Bares e Restaurantes

> **Objetivo desta documentação**: explicar como o projeto funciona **hoje** com base no código existente. Sempre que algo mudar, atualize esta documentação. Se alguma informação estiver ausente/ambígua no repositório, marque como **TODO**.

## A) Visão geral

O projeto oferece uma **roteirização interativa** de bares e restaurantes para rodar no Google Colab. O usuário escolhe uma cidade, busca pontos de interesse (POIs) em serviços públicos, define partida/destino e o sistema calcula uma rota otimizada, exibida em um mapa interativo (`folium`). O fluxo atual é orquestrado pela UI em `ui.py` e por funções de apoio em `geocoding.py`, `data_fetch.py`, `optimization.py` e `mapping.py`.

**Principais casos de uso atuais**:
- Informar município e **buscar POIs** (bares/restaurantes) via Overpass. (`ui.py::on_load_pois()` → `data_fetch.py::coletar_pois()`).
- **Geocodificar** partida/destino e extras via Nominatim/Photon com rate limit. (`geocoding.py::geocode_strict_single()` e `geocoding.py::geocode_fallback_single()`).
- **Calcular matriz de distâncias** com OSRM e aplicar penalização por elevação. (`data_fetch.py::osrm_table()` → `optimization.py::apply_elevation_penalty()`).
- **Resolver a rota** como TSP com início e fim fixos via OR-Tools. (`optimization.py::solve_tsp()`).
- **Renderizar mapa interativo** com marcadores e polyline. (`mapping.py::build_map()` + `mapping.py::fetch_route_geometry_multi()`).
- **UI no Colab** com `ipywidgets`. (`ui.py::launch_ui()`).

## B) Como rodar no Colab (passo a passo)

> **Requisitos**: Python 3.8+, dependências em `requirements.txt`.

1) **Clonar o repositório**
```bash
git clone <URL_DO_REPO>
cd rotadebares
```

2) **Instalar dependências**
```bash
pip install -r requirements.txt
```

3) **Habilitar widgets no Colab**
```python
!jupyter nbextension enable --py widgetsnbextension
```

4) **Ponto de entrada**
- Script principal: `main.py`, que chama `ui.launch_ui()`. (`main.py`).
- **TODO (Notebook principal)**: não há notebook versionado no repo. Criar/definir um notebook oficial de entrada para Colab e documentar aqui.

5) **Executar**
```python
# no Colab
!python main.py
```

> **Observação**: o fluxo é pensado para execução dentro de notebook/Colab (UI com `ipywidgets`). Para rodar a UI em notebook, importe e chame `launch_ui()`:
```python
from ui import launch_ui
launch_ui()
```

## C) Fontes de dados e serviços externos (somente gratuitos)

### 1) Overpass API (POIs)
- **O que fazemos**: buscamos bares/restaurantes e categorias correlatas (bar, pub, cafe, fast_food, nightclub, brewery, shop=alcohol) com filtro por `area` (admin_level 8) ou `bbox` quando disponível. (`data_fetch.py::coletar_pois()`).
- **Limites/boas práticas**:
  - Respeitar timeouts e evitar excesso de requisições.
  - Reaproveitar `area_id` e `bbox` para reduzir carga. (`geocoding.py::get_city_area_id()` + `get_city_bbox()`).
- **Fallbacks**:
  - Se `area_id` não existir, usa `bbox`.
  - Se ambos falharem, tenta `area` com nome. (`data_fetch.py::coletar_pois()`).

### 2) Nominatim/Photon (geocoding via geopy)
- **O que fazemos**: geocoding do endereço com **rate limit** (`geopy.extra.rate_limiter.RateLimiter`) e cache simples. (`geocoding.py`).
- **Limites/boas práticas**:
  - `RateLimiter` com `min_delay_seconds=1` para Nominatim e Photon. (`geocoding.py::geocode_rl`, `photon_geocode_rl`).
  - Usa `viewbox`/`bounded` quando `bbox` está disponível para limitar a cidade.
- **Fallbacks**:
  - `geocode_strict_single()` tenta Nominatim com restrições; se falhar, `geocode_fallback_single()` tenta Nominatim “menos restrito” e depois Photon. (`geocoding.py`).

### 3) Open-Elevation (altitudes)
- **O que fazemos**: busca altitudes em lote para cada ponto. (`data_fetch.py::batch_altitude()`).
- **Limites/boas práticas**:
  - Chamadas em lote (`/api/v1/lookup`) para reduzir requisições.
  - Tratar falhas retornando altitude 0. (`data_fetch.py::batch_altitude()`).
- **Fallbacks**: se a API falhar, retorna 0 para todas as altitudes.

### 4) OSRM público (distâncias e rotas)
- **O que fazemos**:
  - `table`: matriz de distâncias para o TSP. (`data_fetch.py::osrm_table()`).
  - `route`: geometria da rota para desenhar o mapa. (`mapping.py::fetch_route_geometry_multi()`).
- **Limites/boas práticas**:
  - Usar endpoint público `router.project-osrm.org`.
  - Tratar exceções e usar fallback por linha quando a tabela falhar.
- **Fallbacks**:
  - Se `table` falhar, o código tenta obter linha a linha (paralelo com `ThreadPoolExecutor`) e, se ainda falhar, devolve matriz zerada. (`data_fetch.py::osrm_table()`).

## D) Arquitetura e fluxo do pipeline (detalhado)

### Diagrama textual do fluxo
```
Entrada do usuário (ipywidgets)
  → geocode partida/destino (Nominatim/Photon)
  → obter bbox/area_id/polígono da cidade
  → Overpass: coleta de POIs
  → seleção POIs + extras
  → Open-Elevation: altitudes
  → OSRM Table: matriz de distâncias
  → penalização por elevação
  → OR-Tools: TSP com início/fim fixos
  → OSRM Route: geometria da rota
  → Folium: mapa + polyline + marcadores
  → HTML salvo e link para download
```

### Funções/chamadas principais e arquivos
- **UI e orquestração**: `ui.py::on_load_pois()`, `ui.py::on_compute()`, `ui.py::launch_ui()`.
- **Geocoding e limites**: `geocoding.py::geocode_strict_single()`, `geocoding.py::geocode_fallback_single()`, `geocoding.py::get_city_bbox()`, `geocoding.py::get_city_area_id()`.
- **POIs/altitudes/matriz**: `data_fetch.py::coletar_pois()`, `data_fetch.py::batch_altitude()`, `data_fetch.py::osrm_table()`.
- **Roteirização**: `optimization.py::solve_tsp()` e `optimization.py::apply_elevation_penalty()`.
- **Mapa**: `mapping.py::build_map()` e `mapping.py::fetch_route_geometry_multi()`.

### Ordem real de execução (call tree simplificada)
```
main.py
  └─ ui.launch_ui()
       ├─ on_load_pois()  → data_fetch.coletar_pois()
       └─ on_compute()
            ├─ geocoding.geocode_strict_single() / geocode_fallback_single()
            ├─ data_fetch.batch_altitude()
            ├─ data_fetch.osrm_table()
            ├─ optimization.apply_elevation_penalty()
            ├─ optimization.solve_tsp()
            ├─ mapping.build_map()
            └─ folium.Map.save() → arquivo HTML
```

## E) Módulos e responsabilidades (estado atual + alvo)

### Estado atual (módulos existentes)
- `main.py`: ponto de entrada da aplicação. (`main.py`).
- `ui.py`: UI com `ipywidgets` e orquestração do pipeline. (`ui.py`).
- `geocoding.py`: geocoding, bbox/área/polígono e cache. (`geocoding.py`).
- `data_fetch.py`: Overpass, Open-Elevation e OSRM (table). (`data_fetch.py`).
- `mapping.py`: geração do mapa e geometria via OSRM (route). (`mapping.py`).
- `optimization.py`: TSP via OR-Tools + penalização por elevação + opções extras (GLS/Christofides). (`optimization.py`).
- `async_fetch.py`: versões assíncronas de coleta/altitude/OSRM (ainda não integradas à UI). (`async_fetch.py`).
- `benchmark.py`: micro-benchmark dos solvers. (`benchmark.py`).

### Plano de modularização (alvo)
> **Não mover código agora** — apenas plano de como separar responsabilidades.

- `geocoding.py`: manter geocoding + cache + validações de cidade.
- `data_fetch.py`: consolidar Overpass, Open-Elevation, OSRM (table) e sessões HTTP.
- `optimization.py`: centralizar TSP/VRP e configuração OR-Tools (incluindo GLS/Christofides).
- `mapping.py`: isolar geração de mapa e chamadas de rota do OSRM.
- `ui.py`: somente UI e orquestração, importando camadas de serviço.

## F) Algoritmo de roteirização (explicação técnica)

- **Problema**: TSP com **início e fim fixos** (rota simples com pontos intermediários) e peso opcional para elevação. (`optimization.py::solve_tsp()`).
- **Entradas**:
  - Matriz de distâncias do OSRM (`osrm_table`).
  - Lista de coordenadas com altitude (para penalização).
  - Índices de início/fim.
- **Saída**: sequência ordenada de índices visitados (rota). (`solve_tsp`).
- **Função objetivo**: minimizar o custo total da rota na matriz (distância + penalidade de subida). (`apply_elevation_penalty`).
- **Heurísticas/estratégias**:
  - `PATH_CHEAPEST_ARC` como primeira solução. (`optimization.py::solve_tsp()` e `solve_tsp_guided_local_search()`).
  - `GUIDED_LOCAL_SEARCH` disponível, mas **não usado pela UI atualmente**. (`optimization.py::solve_tsp_guided_local_search()`).
  - `christofides_tsp()` disponível como aproximação via NetworkX. (`optimization.py::christofides_tsp()`).
- **Complexidade e gargalos**:
  - **OSRM table**: pode ser o maior gargalo (tempo e limites do endpoint público).
  - **OR-Tools**: cresce com o número de pontos; o tempo limite padrão é 5s.
- **Validação da rota**:
  - Verificar se a rota começa no índice `start` e termina em `end`.
  - Conferir se todos os pontos intermediários aparecem uma única vez.
  - Comparar soma de custos vs. rota não otimizada (ex.: ordem original).

## G) Caching, rate limiting e paralelização

### Cache
- **Onde existe hoje**:
  - `@lru_cache` em `get_city_bbox()`, `get_city_area_id()` e `get_city_polygon()` para reduzir chamadas Overpass/Nominatim. (`geocoding.py`).
  - Cache simples em `_cache_geo` para geocoding de endereços. (`geocoding.py`).
- **Onde faz sentido ampliar** (TODO):
  - Cache de respostas de `osrm_table()` quando mesma lista de pontos é usada.
  - Cache de `coletar_pois()` por cidade.

### Rate limiting
- **Implementado** via `geopy.extra.rate_limiter.RateLimiter` (1s entre requisições) para Nominatim e Photon. (`geocoding.py`).

### Paralelização
- **Implementado**: fallback da OSRM Table usa `ThreadPoolExecutor` para linhas independentes. (`data_fetch.py::osrm_table()`).
- **Assíncrono planejado**: há `async_fetch.py` com versões `async` para Overpass/OSRM/Open-Elevation, **mas ainda não integrado** no fluxo da UI. (`async_fetch.py`).

## H) Mapas e UI

### Folium (mapa)
- **Mapa base**: `folium.Map` centralizado na partida. (`mapping.py::build_map()`).
- **Marcadores**:
  - Partida: ícone verde de play.
  - Destino: ícone vermelho de bandeira.
  - POIs intermediários: `DivIcon` numerado. (`mapping.py::build_map()`).
- **Polyline**: usa geometria do OSRM para a rota completa. (`mapping.py::fetch_route_geometry_multi()`).

### ipywidgets (UI no Colab)
- **Inputs principais**: município, lista de POIs com checkbox, partida/destino, extras e slider de peso de subida. (`ui.py`).
- **Callbacks**:
  - `on_load_pois()` para buscar e listar POIs.
  - `on_compute()` para executar pipeline e salvar HTML. (`ui.py`).
- **Output**: HTML salvo localmente e link para download com `FileLink`. (`ui.py::on_compute()`).

## I) Testes e benchmarking

- **Testes existentes**: `tests/test_geocoding.py`, `tests/test_data_fetch.py`, `tests/test_async_fetch.py`, `tests/test_optimization.py`. (`tests/`).
- **Como rodar testes** (TODO confirmar ambiente Colab):
```bash
pytest -q
```
- **Benchmarking**: script `benchmark.py` mede tempo dos solvers. (`benchmark.py`).
```bash
python benchmark.py
```
- **O que medir** (sugestão):
  - Tempo total da execução do pipeline.
  - Tempo do OSRM Table.
  - Tempo de otimização OR-Tools.

## J) Changelog / Decisões / Known issues

### Decisões de arquitetura (ADR-lite)
- **2024-XX-XX**: UI principal em `ipywidgets` dentro de notebook/Colab. (`ui.py`).
- **2024-XX-XX**: Uso de serviços públicos (Overpass, Nominatim/Photon, Open-Elevation, OSRM). (`data_fetch.py`, `geocoding.py`, `mapping.py`).

### Problemas conhecidos (Known issues)
- **Sem notebook principal versionado**: falta um `.ipynb` oficial para execução no Colab. (TODO).
- **Uso de `networkx`** em `optimization.py` pode exigir dependência extra não listada em `requirements.txt`. (TODO validar). (`optimization.py`).
- **Async não integrado**: `async_fetch.py` não é usado pela UI. (TODO integrar/avaliar). (`async_fetch.py`).

### Roadmap
- Integrar `async_fetch.py` ao fluxo principal.
- Adicionar caching para OSRM Table e POIs por cidade.
- Criar notebook de entrada e documentar.
- Evoluir solver (GLS/Christofides) com escolha na UI.

