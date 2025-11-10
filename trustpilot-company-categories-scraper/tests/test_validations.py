thonfrom src.extractors.filters import FilterEngine

def test_filter_by_rating():
    engine = FilterEngine({"minRating": 4})
    companies = [
        {"ratingValue": "4.5", "country": "US"},
        {"ratingValue": "3.0", "country": "US"}
    ]
    result = engine.apply_filters(companies)
    assert len(result) == 1