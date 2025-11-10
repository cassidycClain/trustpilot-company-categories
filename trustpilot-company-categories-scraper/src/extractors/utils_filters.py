from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

try:
    from .company_parser import Company
except ImportError:
    from company_parser import Company  # type: ignore

logger = logging.getLogger("trustpilot_scraper.filters")

def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def _matches_country(company: Company, country: Optional[str]) -> bool:
    if not country:
        return True
    if not company.country:
        return False
    return company.country.lower() == country.lower()

def _has_min_reviews(company: Company, minimum: Optional[int]) -> bool:
    if minimum is None:
        return True
    if company.reviewCount is None:
        return False
    return company.reviewCount >= minimum

def _meets_min_trust(company: Company, min_trust_score: Optional[float]) -> bool:
    if min_trust_score is None:
        return True
    rating = _safe_float(company.ratingValue)
    if rating is None:
        return False
    return rating >= min_trust_score

def _is_verified(company: Company) -> bool:
    """
    A simple heuristic to determine if a business appears verified.
    Trustpilot indicates this in multiple ways in the UI; since we do not
    have structured verification data, we approximate based on its rating.
    """
    if company.ratingValue is None or company.reviewCount is None:
        return False
    # Treat businesses with 4.0+ rating and > 50 reviews as "verified-like"
    return company.ratingValue >= 4.0 and company.reviewCount >= 50

def apply_company_filters(
    companies: List[Company],
    params: Dict[str, Any],
) -> List[Company]:
    """
    Apply filtering based on input parameters, such as:

      - minTrustScore: minimum ratingValue (float)
      - verifiedOnly: require "verified-like" businesses
      - country: restrict to specific country code
      - minReviews: minimum review count
    """
    min_trust = _safe_float(params.get("minTrustScore"))
    verified_only = bool(params.get("verifiedOnly"))
    min_reviews = params.get("minReviews")
    try:
        min_reviews = int(min_reviews) if min_reviews is not None else None
    except (TypeError, ValueError):
        min_reviews = None

    country = params.get("country")

    filtered: List[Company] = []
    for company in companies:
        if not _meets_min_trust(company, min_trust):
            continue

        if not _matches_country(company, country):
            continue

        if not _has_min_reviews(company, min_reviews):
            continue

        if verified_only and not _is_verified(company):
            continue

        filtered.append(company)

    logger.info(
        "Applied filters (minTrustScore=%s, verifiedOnly=%s, country=%s, minReviews=%s). "
        "Reduced from %d to %d companies.",
        min_trust,
        verified_only,
        country,
        min_reviews,
        len(companies),
        len(filtered),
    )
    return filtered