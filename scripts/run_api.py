from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mf_faq_assistant.phase4_ui.subphase_4_backend.config import load_api_config


def main() -> int:
    import uvicorn

    config = load_api_config()
    uvicorn.run(
        "mf_faq_assistant.phase4_ui.subphase_4_backend.app:app",
        host=config.host,
        port=config.port,
        reload=False,
        app_dir=str(ROOT / "src"),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
