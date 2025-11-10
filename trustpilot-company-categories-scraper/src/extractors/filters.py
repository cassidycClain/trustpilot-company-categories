thonimport logging

class FilterEngine:
    def __init__(self, config):
        self.config = config

    def apply_filters(self, companies):
        min_rating = self.config.get("minRating", 0)
        country = self.config.get("country")
        filtered = []

        for c in companies:
            try:
                rating = float(c.get("ratingValue", 0))
                if rating < min_rating:
                    continue
                if country and c.get("country") != country.upper():
                    continue
                filtered.append(c)
            except ValueError:
                continue

        logging.info(f"Filtered {len(filtered)} out of {len(companies)} companies")
        return filtered