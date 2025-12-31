#!/usr/bin/env python3
import json
import os
import sys
import unicodedata


REGION = "BR-RJ"
DATA_DIR = "data"
GEOJSON_PATH = os.path.join(DATA_DIR, "municipios_rj.geojson")
COMBINED_PATH = os.path.join(DATA_DIR, f"municipio_species_{REGION}.json")
TAXONOMY_PATH = os.path.join(DATA_DIR, f"taxonomy_{REGION}_pt_BR.json")
OUTPUT_HTML = "map_rj.html"

RARITY_VERY_CUTOFF = 5
RARITY_CUTOFF = 10
RARITY_MINOR_CUTOFF = 20


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
        municipio_data[key] = {
            "name": name,
            "code": code,
            "richness": len(species_codes),
            "species": species_list,
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
    h1 {{
      margin: 0 0 6px;
      font-size: 19px;
      letter-spacing: 0.3px;
    }}
    .meta {{
      font-size: 12px;
      color: #555;
    }}
    #map {{
      height: 100%;
      width: 100%;
    }}
    .stat {{
      margin-top: 8px;
      padding: 8px 10px;
      border: 1px solid #e2ded8;
      border-radius: 12px;
      background: var(--panel);
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
      #sidebar h1 {{
        font-size: 16px;
      }}
      .meta {{
        font-size: 10px;
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
    <div id="map"></div>
    <aside id="sidebar">
      <h1>Rio de Janeiro - Municipios</h1>
      <div class="meta">Clique em um municipio para ver as especies (ordenadas por raridade).</div>
      <div class="stat" id="info">
        <strong>Selecione um municipio</strong>
        <div>Riqueza de especies: -</div>
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

    const values = Object.values(MUNICIPIOS).map(d => d.richness);
    const thresholds = buildThresholds(values, COLOR_BINS.length);

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
      const info = document.getElementById('info');
      const list = document.getElementById('species-list');
      if (!data) {{
        info.innerHTML = '<strong>Sem dados</strong><div>Riqueza de especies: -</div>';
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
      info.innerHTML = `<strong>${{data.name}}</strong><div>Codigo: ${{data.code}}</div><div>Riqueza de especies: ${{data.richness}}</div><div>Mostrando: ${{filtered.length}}</div>`;
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
          color: '#4c4c4c',
          weight: 1,
          fillOpacity: 0.75,
          fillColor: getColor(data ? data.richness : null, thresholds)
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
          fillOpacity: 0.75,
          fillColor: getColor(data ? data.richness : null, thresholds)
        }};
      }},
      onEachFeature
    }}).addTo(map);

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
