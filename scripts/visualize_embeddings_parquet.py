from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.decomposition import PCA

EMBEDDINGS_ROOT = Path("data/embeddings")
PARQUET_PATH = EMBEDDINGS_ROOT / "corpus_embeddings.parquet"
HTML_PATH = EMBEDDINGS_ROOT / "embedding_visualization.html"


def load_embedding_records(root: Path) -> list[dict]:
    records: list[dict] = []
    for path in sorted(root.glob("*/*/embeddings.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def export_parquet(records: list[dict]) -> pd.DataFrame:
    rows = []
    for rec in records:
        rows.append(
            {
                "chunk_id": rec["chunk_id"],
                "scheme_id": rec["scheme_id"],
                "scheme_name": rec["scheme_name"],
                "section_name": rec["section_name"],
                "source_url": rec["source_url"],
                "fetched_at": rec["fetched_at"],
                "embedded_text": rec["embedded_text"],
                "embedding_model_id": rec["embedding_model_id"],
                "embedding_dimensions": rec["embedding_dimensions"],
                "embedding": rec["embedding"],
                "expense_ratio": (rec.get("shadow_fields") or {}).get("expense_ratio"),
                "min_sip": (rec.get("shadow_fields") or {}).get("min_sip"),
                "benchmark": (rec.get("shadow_fields") or {}).get("benchmark"),
                "risk": (rec.get("shadow_fields") or {}).get("risk"),
            }
        )
    df = pd.DataFrame(rows)
    PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PARQUET_PATH, index=False)
    return df


def build_visualization_html(df: pd.DataFrame) -> None:
    matrix = pd.DataFrame(df["embedding"].tolist(), index=df.index)
    pca = PCA(n_components=2, random_state=42)
    coords = pca.fit_transform(matrix.values)
    df = df.copy()
    df["pca_x"] = coords[:, 0]
    df["pca_y"] = coords[:, 1]
    df["hover_text"] = df.apply(
        lambda r: (
            f"<b>{r['scheme_name']}</b><br>"
            f"Section: {r['section_name']}<br>"
            f"Expense ratio: {r['expense_ratio']}<br>"
            f"Min SIP: {r['min_sip']}<br>"
            f"Benchmark: {r['benchmark']}<br>"
            f"Risk: {r['risk']}<br>"
            f"Text: {str(r['embedded_text'])[:180]}..."
        ),
        axis=1,
    )

    sections = sorted(df["section_name"].unique())
    color_palette = [
        "#4e79a7",
        "#f28e2b",
        "#e15759",
        "#76b7b2",
        "#59a14f",
        "#edc948",
        "#b07aa1",
        "#ff9da7",
        "#9c755f",
        "#bab0ac",
    ]
    section_colors = {name: color_palette[i % len(color_palette)] for i, name in enumerate(sections)}

    traces_js = []
    for section in sections:
        subset = df[df["section_name"] == section]
        traces_js.append(
            {
                "x": subset["pca_x"].tolist(),
                "y": subset["pca_y"].tolist(),
                "text": subset["hover_text"].tolist(),
                "mode": "markers",
                "type": "scatter",
                "name": section,
                "marker": {
                    "size": 12,
                    "color": section_colors[section],
                    "line": {"width": 1, "color": "#ffffff"},
                },
                "hovertemplate": "%{text}<extra></extra>",
            }
        )

    explained = pca.explained_variance_ratio_
    total_explained = (explained[0] + explained[1]) * 100

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>MF FAQ Embeddings Visualizer</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{
      font-family: Segoe UI, Arial, sans-serif;
      margin: 0;
      background: #0f172a;
      color: #e2e8f0;
    }}
    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
    }}
    p {{
      margin: 0 0 20px;
      color: #94a3b8;
      line-height: 1.5;
    }}
    .card {{
      background: #111827;
      border: 1px solid #1f2937;
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 16px;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }}
    .stat {{
      background: #0b1220;
      border: 1px solid #1e293b;
      border-radius: 10px;
      padding: 12px;
    }}
    .stat .label {{
      color: #94a3b8;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .stat .value {{
      margin-top: 6px;
      font-size: 20px;
      font-weight: 600;
    }}
    #chart {{
      width: 100%;
      height: 680px;
    }}
    code {{
      color: #93c5fd;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Embedding Parquet Visualizer</h1>
    <p>
      2D PCA projection of <code>BAAI/bge-small-en-v1.5</code> vectors from
      <code>{PARQUET_PATH.as_posix()}</code>. Points are colored by section.
      Hover to inspect scheme, shadow fields, and embedded text.
    </p>
    <div class="card">
      <div class="stats">
        <div class="stat"><div class="label">Embeddings</div><div class="value">{len(df)}</div></div>
        <div class="stat"><div class="label">Schemes</div><div class="value">{df['scheme_id'].nunique()}</div></div>
        <div class="stat"><div class="label">Dimensions</div><div class="value">{df['embedding_dimensions'].iloc[0]}</div></div>
        <div class="stat"><div class="label">PCA variance explained</div><div class="value">{total_explained:.1f}%</div></div>
      </div>
    </div>
    <div class="card">
      <div id="chart"></div>
    </div>
  </div>
  <script>
    const traces = {json.dumps(traces_js)};
    const layout = {{
      paper_bgcolor: '#111827',
      plot_bgcolor: '#0b1220',
      font: {{ color: '#e2e8f0' }},
      title: {{
        text: 'Embedding space (PCA 2D)',
        font: {{ size: 18 }}
      }},
      xaxis: {{
        title: 'PCA component 1',
        gridcolor: '#1f2937',
        zerolinecolor: '#334155'
      }},
      yaxis: {{
        title: 'PCA component 2',
        gridcolor: '#1f2937',
        zerolinecolor: '#334155'
      }},
      legend: {{
        orientation: 'h',
        y: -0.15
      }},
      margin: {{ t: 60, r: 20, b: 80, l: 60 }}
    }};
    Plotly.newPlot('chart', traces, layout, {{ responsive: true }});
  </script>
</body>
</html>
"""
    HTML_PATH.write_text(html, encoding="utf-8")


def main() -> int:
    records = load_embedding_records(EMBEDDINGS_ROOT)
    if not records:
        raise SystemExit("No embedding records found under data/embeddings/")

    df = export_parquet(records)
    build_visualization_html(df)
    print(f"Parquet: {PARQUET_PATH}")
    print(f"Visualizer: {HTML_PATH}")
    print(f"Rows: {len(df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
