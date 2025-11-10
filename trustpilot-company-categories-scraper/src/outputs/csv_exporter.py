thonimport csv
import logging
from pathlib import Path

class CSVExporter:
    def export(self, data, output_path):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not data:
            logging.warning("No data to export to CSV.")
            return
        keys = data[0].keys()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
        logging.info(f"CSV exported to {output_path}")