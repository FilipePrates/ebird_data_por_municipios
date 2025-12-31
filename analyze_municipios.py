#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE = "https://api.ebird.org/v2"
REGION = "BR-RJ"
ENV_KEY = "E_BIRD_API_KEY"
ENV_REFRESH = "E_BIRD_REFRESH"
ENV_LOCALE = "E_BIRD_LOCALE"
ENV_CACHE_ONLY = "E_BIRD_CACHE_ONLY"
ENV_USE_COMBINED = "E_BIRD_USE_COMBINED"
DATA_DIR = "data"
DEFAULT_LOCALE = "pt_BR"
RARITY_VERY_CUTOFF = 5
RARITY_CUTOFF = 10


def load_env_key():
    key = os.getenv(ENV_KEY)
    if key:
        return key
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return None
    with open(env_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == ENV_KEY:
                return value.strip().strip('"').strip("'")
    return None


def get_json(path, api_key):
    url = f"{API_BASE}{path}"
    req = Request(url, headers={"X-eBirdApiToken": api_key})
    with urlopen(req, timeout=30) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def get_county_regions(api_key):
    # Subnational2 returns municipios for a state code (BR-RJ).
    return get_json(f"/ref/region/list/subnational2/{REGION}", api_key)


def get_species_list(region_code, api_key):
    return get_json(f"/product/spplist/{region_code}", api_key)


def get_taxonomy(api_key, locale):
    path = f"/ref/taxonomy/ebird?fmt=json&locale={locale}"
    return get_json(path, api_key)


def format_table(rows, headers):
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "+".join("-" * (w + 2) for w in widths)
    def fmt_row(r):
        return "|".join(f" {str(r[i]).ljust(widths[i])} " for i in range(len(r)))
    out = [line, fmt_row(headers), line]
    out.extend(fmt_row(r) for r in rows)
    out.append(line)
    return "\n".join(out)


def write_xlsx(rows, output_dir, municipio_species, taxonomy_map):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:  # pragma: no cover - optional dependency
        print("Missing dependency: openpyxl (install with pip install openpyxl)", file=sys.stderr)
        return None

    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(output_dir, f"species_by_municipio_{REGION}_{ts}.xlsx")

    wb = Workbook()
    build_summary_sheet(wb, rows, municipio_species, taxonomy_map)

    header_fill = PatternFill("solid", fgColor="DDEBF7")
    header_font = Font(bold=True)
    align = Alignment(horizontal="left", vertical="center")
    write_species_sheets(wb, municipio_species, taxonomy_map, header_fill, header_font, align)

    wb.save(out_path)
    return out_path


def load_cache(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_cache(path, payload):
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


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
            "category": item.get("category", ""),
        }
    return by_code


def build_species_counts(municipio_species):
    counts = {}
    for codes in municipio_species.values():
        for code in codes:
            counts[code] = counts.get(code, 0) + 1
    return counts


def rarity_label(count):
    if count <= RARITY_VERY_CUTOFF:
        return f"Muito rara (<= {RARITY_VERY_CUTOFF})"
    if count <= RARITY_CUTOFF:
        return f"Rara (<= {RARITY_CUTOFF})"
    return ""


def write_species_sheets(wb, municipio_species, taxonomy_map, header_fill, header_font, align):
    from openpyxl.styles import PatternFill

    ws = wb.create_sheet("Species_Overview")
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = ws.ORIENTATION_PORTRAIT
    headers = (
        "Species Code",
        "Nome comum",
        "Nome cientifico",
        "Familia",
        "Ordem",
        "Categoria",
        "Municipios",
        "Raridade",
    )
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align

    species_counts = build_species_counts(municipio_species)
    very_rare_fill = PatternFill("solid", fgColor="FFC7CE")
    rare_fill = PatternFill("solid", fgColor="FFE699")
    print(
        f"Rarity buckets: <= {RARITY_VERY_CUTOFF} and <= {RARITY_CUTOFF} municipios.",
        file=sys.stderr,
    )
    for code, count in sorted(species_counts.items(), key=lambda x: x[1], reverse=True):
        info = taxonomy_map.get(code, {})
        rarity = rarity_label(count)
        ws.append(
            (
                code,
                info.get("common", ""),
                info.get("scientific", ""),
                info.get("family", ""),
                info.get("order", ""),
                info.get("category", ""),
                count,
                rarity,
            )
        )
        if count <= RARITY_VERY_CUTOFF:
            fill = very_rare_fill
        elif count <= RARITY_CUTOFF:
            fill = rare_fill
        else:
            fill = None
        if fill:
            for col in range(1, len(headers) + 1):
                ws.cell(row=ws.max_row, column=col).fill = fill

    # Per-municipio sheets with species lists.
    for municipio, species_list in municipio_species.items():
        safe_title = municipio[:31] if municipio else "Municipio"
        mws = wb.create_sheet(safe_title)
        mws.page_setup.paperSize = mws.PAPERSIZE_A4
        mws.page_setup.orientation = mws.ORIENTATION_PORTRAIT
        mws.append(("Species Code", "Nome comum", "Nome cientifico", "Familia", "Ordem", "Categoria"))
        for col in range(1, 7):
            cell = mws.cell(row=1, column=col)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = align
        for code in sorted(species_list):
            info = taxonomy_map.get(code, {})
            count = species_counts.get(code, 0)
            mws.append(
                (
                    code,
                    info.get("common", ""),
                    info.get("scientific", ""),
                    info.get("family", ""),
                    info.get("order", ""),
                    info.get("category", ""),
                )
            )
            if count <= RARITY_VERY_CUTOFF:
                fill = very_rare_fill
            elif count <= RARITY_CUTOFF:
                fill = rare_fill
            else:
                fill = None
            if fill:
                for col in range(1, 7):
                    mws.cell(row=mws.max_row, column=col).fill = fill
        for col_cells in mws.columns:
            max_len = 0
            col_letter = col_cells[0].column_letter
            for cell in col_cells:
                value = cell.value
                if value is None:
                    continue
                max_len = max(max_len, len(str(value)))
            mws.column_dimensions[col_letter].width = min(max_len + 2, 50)


def build_summary_sheet(wb, summary_rows, municipio_species, taxonomy_map):
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    ws = wb.active
    ws.title = "Summary"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = ws.ORIENTATION_PORTRAIT

    header_fill = PatternFill("solid", fgColor="DDEBF7")
    header_font = Font(bold=True)
    align = Alignment(horizontal="left", vertical="center")

    ws["A1"] = "Resumo - RJ (eBird)"
    ws["A1"].font = Font(bold=True, size=14)
    ws.merge_cells("A1:H1")

    def write_table(start_row, start_col, headers, rows):
        for idx, header in enumerate(headers):
            cell = ws.cell(row=start_row, column=start_col + idx, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = align
        for r_idx, row in enumerate(rows, start=1):
            for c_idx, value in enumerate(row):
                ws.cell(row=start_row + r_idx, column=start_col + c_idx, value=value)
        return start_row + len(rows)

    counts = [row[2] for row in summary_rows]
    counts_sorted = sorted(counts)
    total_municipios = len(counts)
    total_species = len({code for codes in municipio_species.values() for code in codes})
    zero_count = sum(1 for c in counts if c == 0)
    avg_count = sum(counts) / total_municipios if total_municipios else 0

    def percentile(p):
        if not counts_sorted:
            return 0
        k = int(round((p / 100) * (len(counts_sorted) - 1)))
        return counts_sorted[k]

    stats_rows = [
        ("Municipios (total)", total_municipios),
        ("Especies (unicas no RJ)", total_species),
        ("Municipios com 0 especies", zero_count),
        ("Media de especies por municipio", round(avg_count, 1)),
        ("Mediana", percentile(50)),
        ("P25", percentile(25)),
        ("P75", percentile(75)),
        ("Maximo", counts_sorted[-1] if counts_sorted else 0),
        ("Minimo", counts_sorted[0] if counts_sorted else 0),
    ]

    ws["A3"] = "Resumo estatistico"
    ws["A3"].font = header_font
    write_table(4, 1, ("Indicador", "Valor"), stats_rows)

    ws["D3"] = "Top 15 municipios"
    ws["D3"].font = header_font
    top_start = 4
    top_rows = [(name, count) for name, _code, count in summary_rows[:15]]
    write_table(top_start, 4, ("Municipio", "Especies"), top_rows)

    if top_rows:
        top_chart = BarChart()
        top_chart.title = "Top 15 municipios"
        top_chart.y_axis.title = "Especies"
        top_chart.x_axis.title = "Municipio"
        data_ref = Reference(ws, min_col=5, min_row=top_start, max_row=top_start + len(top_rows))
        cats_ref = Reference(ws, min_col=4, min_row=top_start + 1, max_row=top_start + len(top_rows))
        top_chart.add_data(data_ref, titles_from_data=True)
        top_chart.set_categories(cats_ref)
        top_chart.height = 8
        top_chart.width = 16
        ws.add_chart(top_chart, "G3")

    bottom_start = 22
    ws[f"A{bottom_start}"] = "Bottom 10 municipios"
    ws[f"A{bottom_start}"].font = header_font
    bottom_rows = list(reversed(summary_rows))[:10]
    write_table(bottom_start + 1, 1, ("Municipio", "Especies"), [(n, c) for n, _code, c in bottom_rows])

    if bottom_rows:
        bottom_chart = BarChart()
        bottom_chart.title = "Bottom 10 municipios"
        bottom_chart.y_axis.title = "Especies"
        bottom_chart.x_axis.title = "Municipio"
        data_ref = Reference(
            ws,
            min_col=2,
            min_row=bottom_start + 1,
            max_row=bottom_start + 1 + len(bottom_rows),
        )
        cats_ref = Reference(
            ws,
            min_col=1,
            min_row=bottom_start + 2,
            max_row=bottom_start + 1 + len(bottom_rows),
        )
        bottom_chart.add_data(data_ref, titles_from_data=True)
        bottom_chart.set_categories(cats_ref)
        bottom_chart.height = 8
        bottom_chart.width = 16
        ws.add_chart(bottom_chart, "D22")

    if counts:
        max_count = max(counts)
        bin_size = 50 if max_count > 200 else 25 if max_count > 100 else 10
        bins = list(range(0, max_count + bin_size, bin_size))
        hist_rows = []
        for i in range(len(bins) - 1):
            lo = bins[i]
            hi = bins[i + 1] - 1
            n = sum(1 for c in counts if lo <= c <= hi)
            hist_rows.append((f"{lo}-{hi}", n))

        hist_start = 40
        ws[f"A{hist_start}"] = "Distribuicao de riqueza"
        ws[f"A{hist_start}"].font = header_font
        write_table(hist_start + 1, 1, ("Faixa", "Municipios"), hist_rows)

        if hist_rows:
            hist_chart = BarChart()
            hist_chart.title = "Distribuicao de riqueza"
            hist_chart.y_axis.title = "Municipios"
            hist_chart.x_axis.title = "Especies"
            data_ref = Reference(
                ws,
                min_col=2,
                min_row=hist_start + 1,
                max_row=hist_start + 1 + len(hist_rows),
            )
            cats_ref = Reference(
                ws,
                min_col=1,
                min_row=hist_start + 2,
                max_row=hist_start + 1 + len(hist_rows),
            )
            hist_chart.add_data(data_ref, titles_from_data=True)
            hist_chart.set_categories(cats_ref)
            hist_chart.height = 8
            hist_chart.width = 16
            ws.add_chart(hist_chart, "D40")

    family_counts = {}
    unique_species = set()
    for codes in municipio_species.values():
        unique_species.update(codes)
    for code in unique_species:
        fam = taxonomy_map.get(code, {}).get("family", "Unknown")
        family_counts[fam] = family_counts.get(fam, 0) + 1
    family_rows = sorted(family_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    fam_start = 58
    ws[f"A{fam_start}"] = "Top 15 familias (RJ)"
    ws[f"A{fam_start}"].font = header_font
    write_table(fam_start + 1, 1, ("Familia", "Especies"), family_rows)

    if family_rows:
        fam_chart = BarChart()
        fam_chart.title = "Top 15 familias"
        fam_chart.y_axis.title = "Especies"
        fam_chart.x_axis.title = "Familia"
        data_ref = Reference(
            ws,
            min_col=2,
            min_row=fam_start + 1,
            max_row=fam_start + 1 + len(family_rows),
        )
        cats_ref = Reference(
            ws,
            min_col=1,
            min_row=fam_start + 2,
            max_row=fam_start + 1 + len(family_rows),
        )
        fam_chart.add_data(data_ref, titles_from_data=True)
        fam_chart.set_categories(cats_ref)
        fam_chart.height = 8
        fam_chart.width = 16
        ws.add_chart(fam_chart, "D58")

    for idx, col_cells in enumerate(ws.columns, start=1):
        max_len = 0
        for cell in col_cells:
            value = cell.value
            if value is None:
                continue
            max_len = max(max_len, len(str(value)))
        col_letter = get_column_letter(idx)
        ws.column_dimensions[col_letter].width = min(max_len + 2, 45)


def main():
    parser = argparse.ArgumentParser(description="eBird species by municipio for Rio de Janeiro.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore cached JSON and re-download all data.",
    )
    parser.add_argument(
        "--locale",
        default=os.getenv(ENV_LOCALE, DEFAULT_LOCALE),
        help="eBird taxonomy locale (default: pt_BR).",
    )
    args = parser.parse_args()

    api_key = load_env_key()
    if not api_key:
        print(f"Missing {ENV_KEY} in environment or .env", file=sys.stderr)
        return 1

    refresh = args.refresh or os.getenv(ENV_REFRESH, "").strip() == "1"
    cache_only = os.getenv(ENV_CACHE_ONLY, "").strip() == "1"
    use_combined = os.getenv(ENV_USE_COMBINED, "1").strip() != "0"

    try:
        print(f"Loading municipios for {REGION}...", file=sys.stderr)
        os.makedirs(DATA_DIR, exist_ok=True)
        counties_cache = os.path.join(DATA_DIR, f"municipios_{REGION}.json")
        counties = None if refresh else load_cache(counties_cache)
        if counties is None:
            if cache_only:
                print(f"Cache only enabled, missing {counties_cache}", file=sys.stderr)
                return 1
            counties = get_county_regions(api_key)
            save_cache(counties_cache, counties)
            print(f"Saved municipios cache to {counties_cache}", file=sys.stderr)
        else:
            print(f"Using cached municipios from {counties_cache}", file=sys.stderr)
    except (HTTPError, URLError) as exc:
        print(f"Failed to load municipios for {REGION}: {exc}", file=sys.stderr)
        return 1

    taxonomy_cache = os.path.join(DATA_DIR, f"taxonomy_{REGION}_{args.locale}.json")
    taxonomy = None if refresh else load_cache(taxonomy_cache)
    if taxonomy is None:
        try:
            if cache_only:
                print(f"Cache only enabled, missing {taxonomy_cache}", file=sys.stderr)
                return 1
            print(f"Loading taxonomy ({args.locale})...", file=sys.stderr)
            taxonomy = get_taxonomy(api_key, args.locale)
            save_cache(taxonomy_cache, taxonomy)
        except (HTTPError, URLError) as exc:
            print(f"Warning: failed to load taxonomy: {exc}", file=sys.stderr)
            taxonomy = []
    taxonomy_map = build_taxonomy_map(taxonomy)

    results = []
    municipio_species = {}
    combined_cache = os.path.join(DATA_DIR, f"municipio_species_{REGION}.json")
    combined = None
    if use_combined and not refresh:
        combined = load_cache(combined_cache)
        if combined:
            print(f"Using combined cache from {combined_cache}", file=sys.stderr)
            for item in combined:
                name = item.get("name")
                code = item.get("code")
                species = item.get("species", [])
                if not name or not code:
                    continue
                results.append((name, code, len(species)))
                municipio_species[name] = species

    if not results:
        total = len(counties)
        print(f"Found {total} municipios. Fetching species lists...", file=sys.stderr)
        combined = []
        for idx, county in enumerate(counties, start=1):
            code = county.get("code")
            name = county.get("name", code)
            if not code:
                continue
            try:
                print(f"[{idx}/{total}] {name} ({code})", file=sys.stderr)
                species_cache = os.path.join(DATA_DIR, f"species_{code}.json")
                species = None if refresh else load_cache(species_cache)
                if species is None:
                    if cache_only:
                        print(f"Cache only enabled, missing {species_cache}", file=sys.stderr)
                        continue
                    species = get_species_list(code, api_key)
                    save_cache(species_cache, species)
                else:
                    print(f"Using cached species list for {code}", file=sys.stderr)
            except (HTTPError, URLError) as exc:
                print(f"Warning: failed for {name} ({code}): {exc}", file=sys.stderr)
                continue
            results.append((name, code, len(species)))
            municipio_species[name] = species
            combined.append({"name": name, "code": code, "species": species})
            # Gentle pacing to avoid rate limiting.
            if idx < total:
                time.sleep(0.2)
        if combined:
            save_cache(combined_cache, combined)
            print(f"Saved combined cache to {combined_cache}", file=sys.stderr)

    results.sort(key=lambda r: r[2], reverse=True)
    headers = ("Municipio", "Code", "Species")
    print(format_table(results, headers))
    out_path = write_xlsx(
        results,
        output_dir="outputs",
        municipio_species=municipio_species,
        taxonomy_map=taxonomy_map,
    )
    if out_path:
        print(f"Saved Excel report to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
