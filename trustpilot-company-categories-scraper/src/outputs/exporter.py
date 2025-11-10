import json
import logging
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable, List

logger = logging.getLogger("trustpilot_scraper.exporter")

def _convert(obj: Any) -> Any:
    """
    Recursively convert dataclasses into plain dicts and ensure that
    everything is JSON-serializable.
    """
    if is_dataclass(obj):
        return {k: _convert(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _convert(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_convert(v) for v in obj]
    return obj

def export_companies(companies: Iterable[Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    serializable: List[Any] = [_convert(c) for c in companies]

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)

    logger.info("Wrote %d companies to %s", len(serializable), output_path)