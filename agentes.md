# Agentes de Automação para Roteirização de Bares e Restaurantes

Este documento define as diretrizes para um agente de IA atuar sobre o repositório de roteirização interativa, assegurando que o programa execute no Google Colaboratory e utilize apenas APIs gratuitas.

## Objetivo

* Automatizar tarefas de desenvolvimento, otimização e testes do script de roteirização.
* Garantir compatibilidade e execução sem custos em ambiente Google Colab.
* Manter uso exclusivo de serviços e APIs gratuitas.

## Ambiente de Execução

* **Python**: versão 3.8 ou superior.
* **Google Colaboratory**: ambiente para execução interativa.
* **Dependências** (ex.: arquivo `requirements.txt`):

  * `requests`
  * `geopy[rate_limiter]`
  * `folium`
  * `ortools`
  * `ipywidgets`
  * `tqdm`
  * `aiohttp`
  * `python-dotenv`
  * `loguru`

## Instruções para o Agente

1. **Clonar Repositório**

   ```bash
   git clone <URL_DO_REPO>
   cd <NOME_DO_REPO>
   ```

2. **Instalar Dependências**

   ```bash
   pip install -r requirements.txt
   ```

   Em Colab, habilitar widgets:

   ```python
   !jupyter nbextension enable --py widgetsnbextension
   ```

3. **Verificar APIs Gratuitas**

   * **Overpass API** (busca de POIs)
   * **OpenStreetMap (Nominatim/Photon)** via `geopy` (respeitar rate limits)
   * **Open-Elevation** (altitudes)
   * **OSRM** (tabela e rotas em `router.project-osrm.org`)

4. **Executar Notebooks de Exemplo**

   * Abrir e rodar os notebooks existentes, validando a geração de mapas e resultados.

5. **Implementar Melhorias Identificadas**

   * **Caching**: usar `@lru_cache` para `get_city_bbox` e geocoding.
   * **Rate Limiting**: aplicar `geopy.extra.rate_limiter.RateLimiter`.
   * **Paralelização**: paralelizar chamadas à OSRM Table com `ThreadPoolExecutor` ou `asyncio`.
   * **Chamada Única OSRM Route**: reconstruir fluxo para um único request de rota completa.
   * **Solver OR-Tools Avançado**: testar `GUIDED_LOCAL_SEARCH`, Christofides (via bibliotecas auxiliares) e comparar resultados.
   * **Modularização**: dividir código em módulos (`geocoding.py`, `data_fetch.py`, `optimization.py`, `mapping.py`, `ui.py`).
   * **Type Hints** e **Doc‑Strings**: adicionar tipagem estática e documentação clara.
   * **AsyncIO**: migrar funções de I/O para `aiohttp` + `asyncio`.

6. **Testes e Benchmarking**

   * Escrever testes unitários para funções puras.
   * Medir tempo de execução antes e depois das otimizações.
   * Validar acurácia das rotas e qualidade dos resultados.

## Checkpoints e Entregáveis

* [ ] Configuração e execução no Colab sem erros.
* [ ] Implementação de cada feature em branches separadas.
* [ ] Pull requests com descrição clara de mudanças.
* [ ] Atualização de `README.md` com instruções de uso.
* [ ] Diagrama de fluxo (PlantUML/Draw\.io) demonstrando pipeline.
* [ ] Relatório de benchmarks comparativos.

---

> **Observação:** todas as chamadas a serviços externos devem utilizar apenas APIs públicas e gratuitas, sem qualquer dependência de serviços pagos ou chaves privadas.
