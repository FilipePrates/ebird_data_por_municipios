# Analise de especies por municipio (RJ) - eBird

Este projeto baixa dados do eBird para o estado do Rio de Janeiro, gera um relatorio em Excel com tabelas e graficos, e cria um mapa HTML interativo por municipio.

## Visualize o mapa localmente

Faça o download do `map_rj.html` (ele fica na raiz do repositório) e abra o arquivo no Chrome/Firefox/Edge para explorar as camadas e filtros no seu navegador padrão.

## O que voce precisa

- Ubuntu
- Python 3 instalado
- Chave do eBird (E_BIRD_API_KEY)

## Passo a passo (Ubuntu)

### 1) Criar e usar um ambiente virtual (venv)

O "venv" cria um espaco separado so para este projeto, evitando problemas no sistema.

No terminal, dentro da pasta do projeto:

```bash
python3 -m venv .venv
. .venv/bin/activate
```

Se der erro de "venv", instale o pacote:

```bash
sudo apt install python3-venv
```

### 2) Ativar o venv e instalar a dependencia do Excel

Ative o venv antes de instalar:

```bash
. .venv/bin/activate
pip install openpyxl
```

### 3) Configurar a chave do eBird

Crie/edite o arquivo `.env` com sua chave:

```
E_BIRD_API_KEY=SUA_CHAVE_AQUI
```

### 4) Rodar o script

```bash
python3 analyze_municipios.py
```

### 5) Gerar o mapa HTML (recomendado)

O mapa HTML mostra os municipios do RJ com riqueza de especies e uma lista filtravel. O arquivo `map_rj.html` pode ser enviado sozinho (ex: WhatsApp).

```bash
python3 make_map_html.py
```

Abra o arquivo no navegador:

```
map_rj.html
```

O mapa agora colore cada municipio segundo o cluster das especies que aparecem ali; a legenda lateral mostra a assinatura das especies que definem cada grupo para facilitar a interpretacao.

O painel de clusters também permite escolher quantos grupos você deseja visualizar (2 a 8); o controle ajusta o traço dos polígonos sem perder o preenchimento de riqueza, então dá pra ver como o “feeling” muda com diferentes granularidades.

> **Preview do mapa**: baixe `map_rj.html` (ele já está gerado na raiz) e abra o arquivo no Chrome/Firefox/Edge para ver o mapa completo. Como o Leaflet depende de scripts externos, visualizá-lo diretamente evita erros como `ReferenceError: L is not defined`.

## Onde ficam os resultados

- Excel gerado: `outputs/`
- Mapa interativo: `map_rj.html`
- Cache dos dados (para nao baixar tudo de novo): `data/`

## Como funciona o cache

O script salva os dados baixados em `data/`. Assim, as proximas execucoes sao bem mais rapidas.

Se quiser baixar tudo novamente:

```bash
E_BIRD_REFRESH=1 python3 analyze_municipios.py
```

## Idioma dos nomes das especies

Por padrao, o script usa nomes comuns em portugues (pt_BR).

Se quiser outro idioma:

```bash
E_BIRD_LOCALE=pt_BR python3 analyze_municipios.py
```

## Problemas comuns

- **Nao gera Excel**: instale o `openpyxl` dentro do venv.
- **Demora muito**: na primeira vez ele baixa tudo e salva em cache. Nas proximas, fica rapido.

## Agrupar municipios pelo “feeling” do bioma

Se quiser separar os municipios por tipos de especies em vez de por riqueza, use `cluster_municipios.py`. O script soma quantas especies de cada ordem (ou familia, passe `--level family`) aparecem em cada municipio, normaliza para evitar que municipios com muitos registros dominem o resultado e aplica um k‑means com distancia de cosseno para aproximar ecoregions naturais. A flag `--level species` roda o mesmo pipeline usando cada especie como categoria, oferecendo a resolucao mais fina (pode gerar clusters diferentes porque representa o “feeling” diretamente). Rode:

```bash
python3 cluster_municipios.py
```

O CSV gerado (`outputs/municipio_clusters.csv`) lista o cluster de cada municipio e a assinatura taxa-top do grupo, e o resumo JSON (`outputs/municipio_clusters_summary.json`) descreve quais municipios e ordens definem cada cluster. Ajuste `--clusters` se quiser mais ou menos grupos e compare com o mapa para validar visualmente.
