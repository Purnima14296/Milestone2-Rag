from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

EMBEDDINGS_ROOT = Path("data/embeddings")
INDEX_DIR = Path("data/index")
VECTORS_PATH = INDEX_DIR / "embeddings.parquet"
META_PATH = INDEX_DIR / "embeddings_meta.parquet"
EMBEDDER_PATH = INDEX_DIR / "embedder.json"
CONFIG_PATH = Path("config/embedding.yaml")


def load_embedding_records(root: Path) -> list[dict]:
    records: list[dict] = []
    for path in sorted(root.glob("*/*/embeddings.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main() -> int:
    records = load_embedding_records(EMBEDDINGS_ROOT)
    if not records:
        raise SystemExit("No embedding records found under data/embeddings/")

    with open(CONFIG_PATH, encoding="utf-8") as f:
        embedder_config = yaml.safe_load(f)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    vectors_df = pd.DataFrame(
        {
            "id": [rec["chunk_id"] for rec in records],
            "embedding": [rec["embedding"] for rec in records],
        }
    )
    vectors_df.to_parquet(VECTORS_PATH, index=False)

    meta_df = pd.DataFrame(
        [
            {
                "id": rec["chunk_id"],
                "scheme_id": rec["scheme_id"],
                "scheme_name": rec["scheme_name"],
                "section_name": rec["section_name"],
                "source_url": rec["source_url"],
                "fetched_at": rec["fetched_at"],
                "embedded_text": rec["embedded_text"],
                "embedding_model_id": rec["embedding_model_id"],
                "embedding_dimensions": rec["embedding_dimensions"],
                "expense_ratio": (rec.get("shadow_fields") or {}).get("expense_ratio"),
                "min_sip": (rec.get("shadow_fields") or {}).get("min_sip"),
                "exit_load": (rec.get("shadow_fields") or {}).get("exit_load"),
                "benchmark": (rec.get("shadow_fields") or {}).get("benchmark"),
                "risk": (rec.get("shadow_fields") or {}).get("risk"),
            }
            for rec in records
        ]
    )
    meta_df.to_parquet(META_PATH, index=False)

    embedder_meta = {
        "embedding_model_id": embedder_config["embedding_model_id"],
        "embedding_dimensions": embedder_config["dimensions"],
        "normalize": embedder_config.get("normalize", True),
        "embedding_count": len(records),
        "vectors_path": VECTORS_PATH.as_posix(),
        "metadata_path": META_PATH.as_posix(),
    }
    EMBEDDER_PATH.write_text(json.dumps(embedder_meta, indent=2), encoding="utf-8")

    print(f"Vectors parquet: {VECTORS_PATH}")
    print(f"Metadata parquet: {META_PATH}")
    print(f"Embedder config: {EMBEDDER_PATH}")
    print(f"Rows: {len(records)}")
    print()
    print("Open in VS Code / Cursor Parquet visualizer:")
    print(f"  {VECTORS_PATH.resolve()}")
    print()
    print("Example SQL query:")
    print(
        "  SELECT id, embedding\n"
        f"  FROM read_parquet('{VECTORS_PATH.resolve().as_posix()}')\n"
        "  LIMIT 1000;"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
