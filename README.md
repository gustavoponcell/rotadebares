# Roteirização de Bares e Restaurantes

Este repositório contém um script interativo para gerar rotas otimizadas de bares e restaurantes utilizando apenas APIs públicas e gratuitas. O código foi pensado para execução no Google Colab.

## Requisitos

- Python 3.8 ou superior
- Dependências listadas em `requirements.txt`

## Instalação

Clone o projeto e instale as dependências:

```bash
git clone <URL_DO_REPO>
cd rotadebares
pip install -r requirements.txt
```

No Colab, habilite os widgets:

```python
!jupyter nbextension enable --py widgetsnbextension
```

## Uso

Execute `main.py` a partir de um notebook (Colab ou Jupyter):

```python
%run main.py
```

Uma interface será exibida para seleção de cidade e POIs. Ao final do processamento será gerado o arquivo `rota_otimizada.html` com o mapa da rota otimizada.

### Algoritmos de Roteirização

O módulo `optimization.py` oferece diferentes estratégias para resolver o TSP. Além de `solve_tsp`, que utiliza a busca padrão do OR-Tools, estão disponíveis:

- `solve_tsp_guided_local_search` – utiliza a metaheurística *GUIDED_LOCAL_SEARCH* do OR-Tools.
- `christofides_tsp` – retorna uma rota aproximada pelo algoritmo de Christofides fornecido pelo NetworkX.

Esses métodos permitem comparar rapidamente a qualidade das rotas geradas.

