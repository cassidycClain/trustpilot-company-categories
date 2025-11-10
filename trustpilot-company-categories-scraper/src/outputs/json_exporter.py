thonimport json
import logging
from pathlib import Path

class JSONExporter:
    def export(self, data, output_path):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logging.info(f"JSON exported to {output_path}")