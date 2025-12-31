# Analise de especies por municipio (RJ) - eBird

Este projeto baixa dados do eBird para o estado do Rio de Janeiro, gera um relatorio em Excel com tabelas e graficos, e cria um mapa HTML interativo por municipio.

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
