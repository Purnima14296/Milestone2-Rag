# 1.6 Indexer

Implemented in `subphase_1_6_indexer/indexer.py`.

Builds `data/index/staging/` then atomically publishes to `data/index/active/`:
- `chroma/` — ChromaDB vector store (cosine similarity)
- `keyword_index.json` — inverted index over shadow fields and terms
- `documents.jsonl` — retrieval manifest

