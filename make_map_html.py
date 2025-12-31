#!/usr/bin/env python3
import json
import os
import sys
import unicodedata
from collections import defaultdict

try:
    from cluster_municipios import assign_clusters
except ImportError:  # pragma: no cover
    assign_clusters = None


REGION = "BR-RJ"
DATA_DIR = "data"
GEOJSON_PATH = os.path.join(DATA_DIR, "municipios_rj.geojson")
COMBINED_PATH = os.path.join(DATA_DIR, f"municipio_species_{REGION}.json")
TAXONOMY_PATH = os.path.join(DATA_DIR, f"taxonomy_{REGION}_pt_BR.json")
OUTPUT_HTML = "map_rj.html"

RARITY_VERY_CUTOFF = 5
RARITY_CUTOFF = 10
RARITY_MINOR_CUTOFF = 20

CLUSTER_LEVELS = ["species", "family", "order"]
CLUSTER_MIN = 2
CLUSTER_MAX = 8
CLUSTER_DEFAULT = 5
CLUSTER_COLORS = [
    "#1b5e20",
    "#ff8f00",
    "#006064",
    "#8e24aa",
    "#c62828",
    "#2e7d32",
    "#6d4c41",
    "#1565c0",
    "#ad1457",
]


def normalize_name(name):
    value = unicodedata.normalize("NFD", name)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in value)
    value = " ".join(value.lower().split())
    return value


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_taxonomy_map(taxonomy):
    by_code = {}
    for item in taxonomy:
        code = item.get("speciesCode")
        if not code:
            continue
        by_code[code] = {
            "scientific": item.get("sciName", ""),
            "common": item.get("comName", ""),
            "family": item.get("familySciName", "") or item.get("familyComName", ""),
            "order": item.get("order", ""),
        }
    return by_code


def rarity_label(count):
    if count <= RARITY_VERY_CUTOFF:
        return f"Muito rara (<= {RARITY_VERY_CUTOFF})"
    if count <= RARITY_CUTOFF:
        return f"Rara (<= {RARITY_CUTOFF})"
    if count <= RARITY_MINOR_CUTOFF:
        return f"Pouco rara (<= {RARITY_MINOR_CUTOFF})"
    return ""


def main():
    if not os.path.exists(GEOJSON_PATH):
        print(f"Missing {GEOJSON_PATH}.", file=sys.stderr)
        return 1
    if not os.path.exists(COMBINED_PATH):
        print(f"Missing {COMBINED_PATH}. Run analyze_municipios.py first.", file=sys.stderr)
        return 1
    if not os.path.exists(TAXONOMY_PATH):
        print(f"Missing {TAXONOMY_PATH}. Run analyze_municipios.py first.", file=sys.stderr)
        return 1

    geojson = load_json(GEOJSON_PATH)
    combined = load_json(COMBINED_PATH)
    taxonomy = load_json(TAXONOMY_PATH)
    taxonomy_map = build_taxonomy_map(taxonomy)

    cluster_history = {level: {} for level in CLUSTER_LEVELS}
    cluster_labels = {level: defaultdict(dict) for level in CLUSTER_LEVELS}
    if assign_clusters:
        for level in CLUSTER_LEVELS:
            for count in range(CLUSTER_MIN, CLUSTER_MAX + 1):
                labels, _, _, summary, _ = assign_clusters(combined, taxonomy_map, level, count)
                cluster_history[level][count] = summary or {}
                for item, label in zip(combined, labels):
                    key = normalize_name(item.get("name"))
                    cluster_labels[level][key][count] = label

    species_counts = {}
    for item in combined:
        for code in item.get("species", []):
            species_counts[code] = species_counts.get(code, 0) + 1

    municipio_data = {}
    for item in combined:
        name = item.get("name")
        code = item.get("code")
        species_codes = item.get("species", [])
        species_list = []
        for sp_code in species_codes:
            info = taxonomy_map.get(sp_code, {})
            count = species_counts.get(sp_code, 0)
            species_list.append(
                {
                    "code": sp_code,
                    "common": info.get("common", ""),
                    "scientific": info.get("scientific", ""),
                    "family": info.get("family", ""),
                    "order": info.get("order", ""),
                    "count": count,
                    "rarity": rarity_label(count),
                }
            )
        species_list.sort(key=lambda s: (s["count"], s["common"]))
        key = normalize_name(name)
        clusters = {level: cluster_labels[level].get(key, {}) for level in CLUSTER_LEVELS}
        default_cluster = clusters.get("species", {}).get(CLUSTER_DEFAULT)
        municipio_data[key] = {
            "name": name,
            "code": code,
            "richness": len(species_codes),
            "species": species_list,
            "clusters": clusters,
            "cluster": default_cluster,
        }

    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>eBird RJ - Mapa de Municipios</title>
  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
    crossorigin=""
  />
  <style>
    :root {{
      --bg: #f4f1ec;
      --ink: #1b1b1b;
      --panel: #ffffff;
      --panel-soft: #fbfaf8;
      --accent: #1d6a5a;
      --accent-2: #ff8f5c;
      --rare: #ffe6a7;
      --very-rare: #ffc1c7;
      --less-rare: #f8f1e6;
      --ring: rgba(29, 106, 90, 0.25);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Ibarra Real Nova", "Georgia", serif;
      color: var(--ink);
      background: var(--bg);
    }}
    #app {{
      display: grid;
      grid-template-columns: 1fr clamp(320px, 34vw, 440px);
      height: 100vh;
      background: radial-gradient(circle at 20% 20%, #fff7e9 0%, transparent 45%),
        radial-gradient(circle at 80% 10%, #eef7f5 0%, transparent 40%),
        var(--bg);
    }}
    #sidebar {{
      padding: 16px 18px 12px;
      overflow: hidden;
      border-left: 1px solid #e2ded8;
      background: var(--panel-soft);
      display: flex;
      flex-direction: column;
      gap: 10px;
      box-shadow: -12px 0 30px rgba(0, 0, 0, 0.04);
    }}
    #map-wrap {{
      position: relative;
      height: 100%;
      width: 100%;
    }}
    #map {{
      height: 100%;
      width: 100%;
    }}
    .stat {{
      margin-top: 8px;
      padding: 6px 8px;
      border: 1px solid #e2ded8;
      border-radius: 12px;
      background: var(--panel);
    }}
    .info-title {{
      font-size: 13px;
      font-weight: 600;
      color: var(--ink);
      margin-bottom: 6px;
    }}
    .info-subtitle {{
      font-size: 11px;
      color: #666;
      margin-bottom: 8px;
    }}
    .info-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
      margin-bottom: 3px;
    }}
    .info-row:last-child {{
      margin-bottom: 0;
    }}
    .info-label {{
      color: #777;
    }}
    .info-value {{
      font-weight: 500;
    }}
    .stat strong {{
      display: block;
      font-size: 15px;
    }}
    .search {{
      display: grid;
      gap: 6px;
    }}
    .search label {{
      font-size: 12px;
      color: #555;
    }}
    .search input {{
      width: 100%;
      padding: 7px 10px;
      border-radius: 10px;
      border: 1px solid #ddd6cc;
      background: #fff;
      font-size: 13px;
      outline: none;
    }}
    .search input:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--ring);
    }}
    .species {{
      margin-top: 8px;
      overflow-y: auto;
      padding-right: 6px;
      flex: 1;
      min-height: 0;
    }}
    .species-item {{
      padding: 8px 10px;
      margin-bottom: 6px;
      border-radius: 10px;
      border: 1px solid #ece7df;
      background: #fff;
      cursor: pointer;
      font-size: 13px;
      line-height: 1.2;
    }}
    .species-item strong {{
      font-size: 13px;
    }}
    .species-item em {{
      font-size: 12px;
    }}
    .species-item.active {{
      border-color: #2a5f57;
      box-shadow: 0 0 0 2px rgba(29, 106, 90, 0.12);
    }}
    .species-item.rare {{
      background: var(--rare);
    }}
    .species-item.very-rare {{
      background: var(--very-rare);
    }}
    .species-item.less-rare {{
      background: var(--less-rare);
    }}
    .badge {{
      display: inline-block;
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 999px;
      background: #1d6a5a;
      color: #fff;
      margin-left: 6px;
    }}
    .note {{
      margin-top: 8px;
      font-size: 11px;
      color: #666;
    }}
    .cluster-bar {{
      padding: 8px 8px 6px;
      background: rgba(255, 255, 255, 0.92);
      border-radius: 12px;
      box-shadow: 0 10px 24px rgba(0, 0, 0, 0.12);
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 12px;
      color: #555;
      backdrop-filter: blur(6px);
    }}
    .cluster-bar.map-legend {{
      position: absolute;
      bottom: 16px;
      left: 16px;
      z-index: 500;
      width: min(240px, 72vw);
      pointer-events: auto;
    }}
    .cluster-legend-heading {{
      font-weight: 600;
      font-size: 13px;
    }}
    .cluster-legend-item {{
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      padding: 4px 6px;
      border-radius: 10px;
      transition: background 0.2s ease;
    }}
    .cluster-legend-item:hover {{
      background: rgba(0, 0, 0, 0.06);
    }}
    .cluster-legend-item.active {{
      background: rgba(0, 0, 0, 0.12);
    }}
    .cluster-legend-color {{
      width: 14px;
      height: 14px;
      border-radius: 999px;
      display: inline-block;
    }}
    .cluster-legend-meta {{
      display: flex;
      flex-direction: column;
      line-height: 1.2;
    }}
    .cluster-legend-items {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .cluster-selector {{
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}
    .cluster-selector label {{
      font-size: 11px;
      color: #555;
      font-weight: 500;
    }}
    .cluster-selector input {{
      width: 100%;
      accent-color: var(--accent);
    }}
    .cluster-selector select {{
      width: 100%;
      padding: 4px 6px;
      border-radius: 8px;
      border: 1px solid #ddd6cc;
      background: #fff;
      font-size: 12px;
      font-family: inherit;
    }}
    @media (max-width: 1200px) {{
      #app {{
        grid-template-columns: 1fr clamp(300px, 38vw, 380px);
      }}
    }}
    @media (max-width: 900px) {{
      #app {{
        grid-template-columns: 1fr;
        grid-template-rows: 30vh 70vh;
      }}
      #sidebar {{
        border-left: none;
        border-top: 1px solid #e2ded8;
        box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.06);
      }}
      .stat {{
        margin-top: 4px;
        padding: 5px 7px;
      }}
      .stat strong {{
        font-size: 13px;
      }}
      .search input {{
        padding: 5px 7px;
        font-size: 11px;
      }}
      .species {{
        margin-top: 4px;
      }}
      .species-item {{
        padding: 5px 7px;
        margin-bottom: 4px;
        font-size: 12px;
      }}
      .species-item strong {{
        font-size: 12px;
      }}
      .species-item em {{
        font-size: 11px;
      }}
      .badge {{
        font-size: 9px;
        padding: 1px 4px;
        margin-left: 4px;
      }}
      .species {{
        padding-bottom: 16px;
      }}
    }}
  </style>
</head>
<body>
  <div id="app">
    <div id="map-wrap">
      <div id="map"></div>
      <div class="cluster-bar map-legend" id="cluster-legend">
        <div class="cluster-legend-heading">Agrupamentos (k-means)</div>
        <div class="cluster-legend-items" id="cluster-legend-items"></div>
        <div class="cluster-selector">
          <label for="cluster-level">Nivel</label>
          <select id="cluster-level">
            <option value="species" selected>Especie</option>
            <option value="family">Familia</option>
            <option value="order">Ordem</option>
          </select>
        </div>
        <div class="cluster-selector">
          <label for="cluster-count">
            Clusters: <span id="cluster-count-label">{CLUSTER_DEFAULT}</span>
          </label>
          <input
            id="cluster-count"
            type="range"
            min="{CLUSTER_MIN}"
            max="{CLUSTER_MAX}"
            value="{CLUSTER_DEFAULT}"
          />
        </div>
      </div>
    </div>
    <aside id="sidebar">
      <div class="stat" id="info">
        <div class="info-title" id="info-title">Selecione um municipio</div>
        <div class="info-subtitle" id="info-subtitle">Clique em um municipio para ver as especies (ordenadas por raridade).</div>
        <div class="info-row">
          <span class="info-label">Riqueza</span>
          <span class="info-value" id="info-richness">-</span>
        </div>
        <div class="info-row">
          <span class="info-label">Cluster</span>
          <span class="info-value" id="info-cluster">—</span>
        </div>
        <div class="info-row">
          <span class="info-label">Assinatura</span>
          <span class="info-value" id="info-signature">—</span>
        </div>
        <div class="info-row">
          <span class="info-label">Mostrando</span>
          <span class="info-value" id="info-count">0</span>
        </div>
      </div>
      <div class="search">
        <label for="species-search">Buscar especies</label>
        <input id="species-search" type="search" placeholder="Digite nome comum ou cientifico" />
      </div>
      <div class="note">Cores de raridade: muito rara (<= {RARITY_VERY_CUTOFF}), rara (<= {RARITY_CUTOFF}) e pouco rara (<= {RARITY_MINOR_CUTOFF}).</div>
      <div class="species" id="species-list"></div>
    </aside>
  </div>

  <script
    src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
    crossorigin=""
  ></script>
  <script>
    const GEOJSON = {json.dumps(geojson, ensure_ascii=False)};
    const MUNICIPIOS = {json.dumps(municipio_data, ensure_ascii=False)};
    const CLUSTER_HISTORY = {json.dumps(cluster_history, ensure_ascii=False)};
    const CLUSTER_COLORS = {json.dumps(CLUSTER_COLORS)};
    const CLUSTER_MIN = {CLUSTER_MIN};
    const CLUSTER_MAX = {CLUSTER_MAX};
    const CLUSTER_DEFAULT = {CLUSTER_DEFAULT};
    const CLUSTER_LEVELS = {json.dumps(CLUSTER_LEVELS)};
    const RARITY_VERY_CUTOFF = {RARITY_VERY_CUTOFF};
    const RARITY_CUTOFF = {RARITY_CUTOFF};
    const RARITY_MINOR_CUTOFF = {RARITY_MINOR_CUTOFF};

    function keyName(name) {{
      return name.normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .replace(/[^a-z0-9 ]/g, ' ')
        .replace(/\\s+/g, ' ')
        .trim();
    }}

    const COLOR_BINS = ['#f2c14e', '#e6a64b', '#d48e52', '#c2785d', '#ae6263', '#8e4b62', '#6d3856'];

    function buildThresholds(values, bins) {{
      const sorted = values.slice().sort((a, b) => a - b);
      const thresholds = [];
      for (let i = 1; i < bins; i += 1) {{
        const idx = Math.floor((i / bins) * (sorted.length - 1));
        thresholds.push(sorted[idx]);
      }}
      return thresholds;
    }}

    function getColor(value, thresholds) {{
      if (value == null) return '#d6d3cc';
      for (let i = 0; i < thresholds.length; i += 1) {{
        if (value <= thresholds[i]) return COLOR_BINS[i];
      }}
      return COLOR_BINS[COLOR_BINS.length - 1];
    }}

    let currentClusterCount = CLUSTER_DEFAULT;
    let currentClusterLevel = 'species';
    let activeClusterFilter = null;

    function getClusterLabel(data) {{
      if (!data || !data.clusters) return null;
      const levelBuckets = data.clusters[currentClusterLevel] || {{}};
      return levelBuckets[currentClusterCount];
    }}

    function getClusterColor(data) {{
      const label = getClusterLabel(data);
      if (label == null || !CLUSTER_COLORS.length) return null;
      return CLUSTER_COLORS[label % CLUSTER_COLORS.length];
    }}

    function getMunicipioStrokeColor(data) {{
      return getClusterColor(data) || '#4c4c4c';
    }}

    function getClusterSummary(count) {{
      const level = CLUSTER_HISTORY[currentClusterLevel] || {{}};
      return level[count] || {{}};
    }}

    const richnessValues = Object.values(MUNICIPIOS)
      .map(d => d.richness)
      .filter(value => typeof value === 'number');
    const minRichness = Math.min(...richnessValues);
    const maxRichness = Math.max(...richnessValues);

    function getRichnessOpacity(value) {{
      if (value == null || !Number.isFinite(value)) return 0.2;
      if (maxRichness <= minRichness) return 0.75;
      const ratio = (value - minRichness) / (maxRichness - minRichness);
      const boosted = Math.sqrt(Math.max(0, ratio));
      return 0.2 + boosted * 0.75;
    }}

    function getMunicipioFillColor(data) {{
      return getClusterColor(data) || getColor(data ? data.richness : null, thresholds);
    }}

    function getMunicipioFillOpacity(data) {{
      if (getClusterColor(data)) return getRichnessOpacity(data.richness);
      return 0.75;
    }}

    function renderClusterLegend(count = currentClusterCount) {{
      const list = document.getElementById('cluster-legend-items');
      if (!list) return;
      list.innerHTML = '';
      const summary = getClusterSummary(count);
      const entries = Object.entries(summary)
        .map(([label, info]) => {{
          return {{ label: Number(label), info }};
        }})
        .sort((a, b) => a.label - b.label);
      if (!entries.length) {{
        const empty = document.createElement('div');
        empty.textContent = 'Dados de cluster nao disponiveis';
        empty.style.fontSize = '11px';
        list.appendChild(empty);
        return;
      }}
      entries.forEach(({{ label, info }}) => {{
        const item = document.createElement('div');
        item.className = 'cluster-legend-item';
        item.dataset.cluster = label;
        if (activeClusterFilter === label) {{
          item.classList.add('active');
        }}
        const color = CLUSTER_COLORS[label % CLUSTER_COLORS.length] || '#d6d3cc';
        item.innerHTML = `
          <span class="cluster-legend-color" style="background:${{color}};"></span>
          <span class="cluster-legend-meta">
            <strong>Cluster ${{label}}</strong>
            <span>${{(info.signature || []).join(', ') || 'sem assinatura'}}</span>
          </span>
        `;
        item.addEventListener('click', () => {{
          if (activeClusterFilter === label) {{
            activeClusterFilter = null;
          }} else {{
            activeClusterFilter = label;
          }}
          renderClusterLegend(currentClusterCount);
          applyClusterStyles();
        }});
        list.appendChild(item);
      }});
    }}

    function applyClusterStyles() {{
      if (!geojson) return;
      geojson.eachLayer(layer => {{
        const name = layer.feature.properties.name || '';
        const data = MUNICIPIOS[keyName(name)];
        const clusterLabel = getClusterLabel(data);
        const isFiltered = activeClusterFilter != null;
        const isMatch = clusterLabel === activeClusterFilter;
        if (activeLayer === layer) {{
          layer.setStyle({{
            color: '#111',
            weight: 3,
            fillOpacity: Math.min(0.95, getMunicipioFillOpacity(data) + 0.15),
            fillColor: getMunicipioFillColor(data),
          }});
          return;
        }}
        layer.setStyle({{
          color: getMunicipioStrokeColor(data),
          weight: isFiltered && !isMatch ? 0.5 : 1,
          fillOpacity: isFiltered && !isMatch ? 0.15 : getMunicipioFillOpacity(data),
          fillColor: getMunicipioFillColor(data),
        }});
      }});
    }}

    function setClusterCount(value) {{
      currentClusterCount = Math.min(Math.max(value, CLUSTER_MIN), CLUSTER_MAX);
      const label = document.getElementById('cluster-count-label');
      if (label) {{
        label.textContent = `${{currentClusterCount}}`;
      }}
      activeClusterFilter = null;
      renderClusterLegend(currentClusterCount);
      applyClusterStyles();
    }}

    function setClusterLevel(level) {{
      if (!CLUSTER_LEVELS.includes(level)) return;
      currentClusterLevel = level;
      activeClusterFilter = null;
      renderClusterLegend(currentClusterCount);
      applyClusterStyles();
    }}

    const thresholds = buildThresholds(richnessValues, COLOR_BINS.length);

    const map = L.map('map').setView([-22.4, -42.5], 7.4);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 11,
      attribution: '&copy; OpenStreetMap'
    }}).addTo(map);

    const layerByKey = {{}};
    let activeLayer = null;
    let activeData = null;
    let activeSpecies = null;

    const speciesToMunicipios = (() => {{
      const index = {{}};
      Object.values(MUNICIPIOS).forEach(muni => {{
        muni.species.forEach(sp => {{
          if (!index[sp.code]) index[sp.code] = [];
          index[sp.code].push(keyName(muni.name));
        }});
      }});
      return index;
    }})();

    function renderSpeciesList(data, query) {{
      const list = document.getElementById('species-list');
      if (!data) {{
        const titleEl = document.getElementById('info-title');
        const richnessEl = document.getElementById('info-richness');
        const clusterEl = document.getElementById('info-cluster');
        const signatureEl = document.getElementById('info-signature');
        const countEl = document.getElementById('info-count');
        if (titleEl) titleEl.textContent = 'Sem dados';
        if (richnessEl) richnessEl.textContent = '-';
        if (clusterEl) clusterEl.textContent = '—';
        if (signatureEl) signatureEl.textContent = '—';
        if (countEl) countEl.textContent = '0';
        list.innerHTML = '';
        return;
      }}
      const normalized = (query || '').trim().toLowerCase();
      const filtered = data.species.filter(item => {{
        if (!normalized) return true;
        const common = (item.common || '').toLowerCase();
        const scientific = (item.scientific || '').toLowerCase();
        return common.includes(normalized) || scientific.includes(normalized);
      }});
      const selectedCluster = getClusterLabel(data);
      const summary = getClusterSummary(currentClusterCount)[selectedCluster] || {{ signature: [] }};
      const clusterSignature = summary.signature.length ? summary.signature.join(', ') : 'sem assinatura';
      const titleEl = document.getElementById('info-title');
      const richnessEl = document.getElementById('info-richness');
      const clusterEl = document.getElementById('info-cluster');
      const signatureEl = document.getElementById('info-signature');
      const countEl = document.getElementById('info-count');
      if (titleEl) titleEl.textContent = data.name;
      if (richnessEl) richnessEl.textContent = data.richness;
      if (clusterEl) clusterEl.textContent = selectedCluster != null ? `Cluster ${{selectedCluster}}` : '—';
      if (signatureEl) signatureEl.textContent = clusterSignature;
      if (countEl) countEl.textContent = filtered.length;
      list.innerHTML = '';
      filtered.forEach(item => {{
        const div = document.createElement('div');
        const classes = ['species-item'];
        if (item.count <= RARITY_VERY_CUTOFF) classes.push('very-rare');
        else if (item.count <= RARITY_CUTOFF) classes.push('rare');
        else if (item.count <= RARITY_MINOR_CUTOFF) classes.push('less-rare');
        if (activeSpecies === item.code) classes.push('active');
        div.className = classes.join(' ');
        div.dataset.code = item.code;
        const rarityBadgeColor = item.count <= RARITY_VERY_CUTOFF
          ? '#9f1239'
          : item.count <= RARITY_CUTOFF
            ? '#b45309'
            : '#7c2d12';
        div.innerHTML = `
          <strong>${{item.common || item.scientific}}</strong>
          <div><em>${{item.scientific}}</em></div>
          <div>${{item.family}} · ${{item.order}}</div>
          <span class="badge">${{item.count}} municipios</span>
          ${{item.rarity ? `<span class="badge" style="background:${{rarityBadgeColor}};">${{item.rarity}}</span>` : ''}}
        `;
        div.addEventListener('click', () => {{
          toggleSpeciesHighlight(item.code);
        }});
        list.appendChild(div);
      }});
    }}

    function applySpeciesHighlight(code) {{
      const keys = new Set(speciesToMunicipios[code] || []);
      geojson.eachLayer(layer => {{
        const name = layer.feature.properties.name || '';
        const key = keyName(name);
        const data = MUNICIPIOS[key];
        const baseStyle = {{
        color: getMunicipioStrokeColor(data),
        weight: 1,
        fillOpacity: getMunicipioFillOpacity(data),
        fillColor: getMunicipioFillColor(data)
      }};
        if (keys.has(key)) {{
          layer.setStyle({{
            ...baseStyle,
            color: '#1c413b',
            weight: 2.2,
            fillOpacity: 0.9
          }});
        }} else {{
          layer.setStyle({{
            ...baseStyle,
            color: '#b9b6b0',
            weight: 0.6,
            fillOpacity: 0.25
          }});
        }}
      }});
    }}

    function clearSpeciesHighlight() {{
      geojson.eachLayer(layer => {{
        geojson.resetStyle(layer);
      }});
    }}

    function toggleSpeciesHighlight(code) {{
      if (activeSpecies === code) {{
        activeSpecies = null;
        clearSpeciesHighlight();
        renderSpeciesList(activeData, document.getElementById('species-search').value);
        return;
      }}
      activeSpecies = code;
      applySpeciesHighlight(code);
      renderSpeciesList(activeData, document.getElementById('species-search').value);
    }}

    function updateSidebar(data) {{
      activeData = data;
      const query = document.getElementById('species-search').value;
      renderSpeciesList(data, query);
    }}

    function onEachFeature(feature, layer) {{
      const name = feature.properties.name || '';
      const data = MUNICIPIOS[keyName(name)];

      layer.on('click', () => {{
        if (activeLayer) {{
          geojson.resetStyle(activeLayer);
        }}
        activeLayer = layer;
        layer.setStyle({{ weight: 3, color: '#111' }});
        if (activeSpecies) {{
          const hasSpecies = data && data.species.some(item => item.code === activeSpecies);
          if (hasSpecies) {{
            applySpeciesHighlight(activeSpecies);
          }} else {{
            activeSpecies = null;
            clearSpeciesHighlight();
          }}
        }}
        updateSidebar(data);
      }});

      layer.bindTooltip(name, {{ sticky: true }});
      layerByKey[keyName(name)] = layer;
    }}

    const geojson = L.geoJSON(GEOJSON, {{
      style: (feature) => {{
        const name = feature.properties.name || '';
        const data = MUNICIPIOS[keyName(name)];
        return {{
          color: '#4c4c4c',
          weight: 1,
          fillOpacity: getMunicipioFillOpacity(data),
          fillColor: getMunicipioFillColor(data)
        }};
      }},
      onEachFeature
    }}).addTo(map);

    const clusterInput = document.getElementById('cluster-count');
    const clusterLevel = document.getElementById('cluster-level');
    if (clusterInput) {{
      if (!Object.keys(CLUSTER_HISTORY).length) {{
        clusterInput.setAttribute('disabled', 'disabled');
      }}
      clusterInput.addEventListener('input', (event) => {{
        if (!event.target) return;
        setClusterCount(Number(event.target.value));
      }});
    }}
    if (clusterLevel) {{
      clusterLevel.addEventListener('change', (event) => {{
        if (!event.target) return;
        setClusterLevel(event.target.value);
      }});
    }}
    setClusterCount(CLUSTER_DEFAULT);

    document.getElementById('species-search').addEventListener('input', (event) => {{
      if (!activeData) return;
      renderSpeciesList(activeData, event.target.value);
    }});
  </script>
</body>
</html>
"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"Wrote {OUTPUT_HTML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
