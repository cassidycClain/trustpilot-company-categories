thonimport pytest
from src.extractors.company_parser import CompanyParser
from src.extractors.review_parser import ReviewParser

def test_company_parser_returns_data():
    parser = CompanyParser({"category": "gaming", "country": "us"})
    data = parser._parse_page("<html></html>")
    assert isinstance(data, list)
    assert "name" in data[0]

def test_review_parser_adds_reviews():
    parser = ReviewParser({"withLastReviews": True})
    companies = [{"ID": "1", "name": "Test"}]
    enriched = parser.append_reviews(companies)
    assert "reviews" in enriched[0]
    assert len(enriched[0]["reviews"]) > 0