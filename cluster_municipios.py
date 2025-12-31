#!/usr/bin/env python3
"""Cluster municípios by their species composition to surface ecoregion-like groups."""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
import sys

DATA_DIR = Path("data")
OUTPUTS_DIR = Path("outputs")

CLUSTER_LEVEL = "species"
CLUSTER_MIN = 2
CLUSTER_MAX = 8
CLUSTER_DEFAULT = 5


def load_taxonomy() -> dict[str, dict[str, str]]:
    path = DATA_DIR / "taxonomy_BR-RJ_pt_BR.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    mapping: dict[str, dict[str, str]] = {}
    for entry in data:
        code = entry.get("speciesCode")
        if not code:
            continue
        mapping[code] = {
            "order": entry.get("order") or "unknown",
            "family": entry.get("familySciName") or entry.get("familyComName") or "unknown",
        }
    return mapping


def load_municipios() -> list[dict]:
    path = DATA_DIR / "municipio_species_BR-RJ.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_feature_matrix(
    municipios: list[dict], taxonomy: dict[str, dict[str, str]], level_key: str
) -> tuple[list[list[float]], list[str]]:
    level_rows: list[Counter[str]] = []
    level_values: set[str] = set()
    for muni in municipios:
        counts: Counter[str] = Counter()
        for code in muni.get("species", []):
            if level_key == "species":
                value = code
            else:
                value = taxonomy.get(code, {}).get(level_key, "unknown")
            counts[value] += 1
        level_rows.append(counts)
        level_values.update(counts.keys())
    level_names = sorted(level_values)
    matrix: list[list[float]] = []
    for counts in level_rows:
        row = [float(counts.get(level_name, 0)) for level_name in level_names]
        matrix.append(row)
    return matrix, level_names


def normalize_rows(rows: list[list[float]]) -> list[list[float]]:
    normalized: list[list[float]] = []
    for row in rows:
        total = sum(row)
        if total <= 0:
            normalized.append([0.0] * len(row))
            continue
        normalized.append([value / total for value in row])
    return normalized


def unit_vector(row: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in row))
    if magnitude <= 0:
        return [0.0] * len(row)
    return [value / magnitude for value in row]


def cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 1.0
    return 1.0 - dot / (mag_a * mag_b)


def kmeans(
    vectors: list[list[float]], k: int, max_iter: int = 50
) -> list[int]:
    if not vectors:
        return []
    k = min(k, len(vectors))
    random.seed(0)
    centers = [unit_vector(list(vectors[idx])) for idx in random.sample(range(len(vectors)), k)]
    labels: list[int] = [0] * len(vectors)
    for _ in range(max_iter):
        new_labels = []
        clusters: list[list[list[float]]] = [[] for _ in range(k)]
        for vector in vectors:
            distances = [cosine_distance(vector, center) for center in centers]
            idx = min(range(k), key=lambda index: distances[index])
            clusters[idx].append(vector)
            new_labels.append(idx)
        if new_labels == labels:
            break
        labels = new_labels
        for idx in range(k):
            if not clusters[idx]:
                centers[idx] = unit_vector(random.choice(vectors))
                continue
            averaged = [sum(values) / len(clusters[idx]) for values in zip(*clusters[idx])]
            centers[idx] = unit_vector(averaged)
    return labels


def top_signature(
    vector: list[float],
    display_names: list[str],
    limit: int = 3,
) -> list[str]:
    ordered = sorted(range(len(display_names)), key=lambda i: vector[i], reverse=True)
    return [display_names[idx] for idx in ordered[:limit] if vector[idx] > 0]


def build_display_names(
    level_key: str,
    level_names: list[str],
    taxonomy: dict[str, dict[str, str]],
) -> list[str]:
    if level_key != "species":
        return level_names
    display = []
    for code in level_names:
        info = taxonomy.get(code, {})
        name = info.get("common") or info.get("scientific") or code
        display.append(name)
    return display


def summarize_clusters(
    municipios: list[dict], labels: list[int], normalized: list[list[float]], level_names: list[str]
) -> dict[int, dict]:
    summary: dict[int, dict] = {}
    for cluster in sorted(set(labels)):
        indices = [idx for idx, label in enumerate(labels) if label == cluster]
        cluster_rows = [normalized[idx] for idx in indices]
        means = [0.0] * len(level_names)
        if cluster_rows:
            for row in cluster_rows:
                for idx, value in enumerate(row):
                    means[idx] += value
            size = len(cluster_rows)
            means = [value / size for value in means]
        ordered = sorted(range(len(level_names)), key=lambda i: means[i], reverse=True)
        signature = [level_names[idx] for idx in ordered[:3] if means[idx] > 0]
        summary[cluster] = {
            "municipios": [municipios[idx]["name"] for idx in indices],
            "signature": signature,
            "size": len(indices),
        }
    return summary


def assign_clusters(
    municipios: list[dict],
    taxonomy: dict[str, dict[str, str]],
    level_key: str = "order",
    cluster_count: int = 5,
) -> tuple[list[int], list[list[float]], list[str], dict[int, dict], list[list[str]]]:
    feature_rows, level_names = build_feature_matrix(municipios, taxonomy, level_key)
    normalized = normalize_rows(feature_rows)
    labels = kmeans(normalized, cluster_count)
    display_names = build_display_names(level_key, level_names, taxonomy)
    signatures = [top_signature(row, display_names) for row in normalized]
    summary = summarize_clusters(municipios, labels, normalized, display_names)
    return labels, normalized, level_names, summary, signatures


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    headers = list(rows[0].keys())
    with path.open("w", encoding="utf-8") as fh:
        fh.write(";".join(headers) + "\n")
        for row in rows:
            fh.write(";".join(row[h] for h in headers) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Approximate ecoregion-style clusters based on species composition."
    )
    parser.add_argument(
        "--level",
        choices=["order", "family", "species"],
        default="order",
        help="Taxonomic level to describe species (default: order).",
    )
    parser.add_argument(
        "--clusters",
        type=int,
        default=5,
        help="Rough target number of clusters to produce.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUTS_DIR / "municipio_clusters.csv",
        help="CSV file where each municipio gets a cluster assignment",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    taxonomy = load_taxonomy()
    municipios = load_municipios()
    labels, normalized, level_names, summary, signatures = assign_clusters(
        municipios, taxonomy, args.level, args.clusters
    )
    OUTPUTS_DIR.mkdir(exist_ok=True)
    rows: list[dict[str, str]] = []
    for idx, (muni, label) in enumerate(zip(municipios, labels)):
        rows.append(
            {
                "cluster": str(label),
                "code": muni["code"],
                "municipio": muni["name"],
                "richness": str(len(muni.get("species", []))),
                "signature": ",".join(signatures[idx]),
            }
        )
    write_csv(args.output, rows)
    summary_path = args.output.with_name(f"{args.output.stem}_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {args.output} and {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
