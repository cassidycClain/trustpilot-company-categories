from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("trustpilot_scraper.reviews")

@dataclass
class Consumer:
    id: Optional[str]
    displayName: Optional[str]
    imageUrl: Optional[str]
    isVerified: Optional[bool]
    numberOfReviews: Optional[int]
    countryCode: Optional[str]

@dataclass
class Review:
    id: Optional[str]
    text: Optional[str]
    title: Optional[str]
    rating: Optional[int]
    date: Dict[str, Any]
    consumer: Consumer

def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None

def _parse_date_iso(raw: str) -> Dict[str, Any]:
    """
    Normalize any parseable date string into the JSON structure used in the README.
    """
    created_at: Optional[str] = None
    try:
        # Trustpilot typically uses ISO timestamps already
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        created_at = dt.isoformat()
    except Exception:
        created_at = raw
    return {"createdAt": created_at}

def _extract_consumer_from_card(card) -> Consumer:
    # HTML is likely to change over time; we defensively look for common patterns.
    name_el = card.select_one("[data-consumer-name]") or card.select_one(
        ".consumer-information__name"
    )
    name = name_el.get_text(strip=True) if name_el else None

    img_el = card.select_one("img")
    image_url = img_el["src"] if img_el and img_el.has_attr("src") else None

    country_el = card.select_one("[data-consumer-country]") or card.select_one(
        ".consumer-information__details"
    )
    country_code = None
    if country_el:
        country_text = country_el.get_text(strip=True)
        if country_text and len(country_text) <= 3:
            country_code = country_text.upper()

    reviews_count_el = card.select_one("[data-consumer-reviews-count]")
    number_of_reviews = _safe_int(
        reviews_count_el.get("data-consumer-reviews-count")
        if reviews_count_el
        else None
    )

    is_verified = bool(card.select_one(".badge--verified") or card.select_one(
        "[data-review-verified='true']"
    ))

    return Consumer(
        id=None,
        displayName=name,
        imageUrl=image_url,
        isVerified=is_verified,
        numberOfReviews=number_of_reviews,
        countryCode=country_code,
    )

def _extract_rating_from_card(card) -> Optional[int]:
    rating_el = card.select_one("[data-rating]") or card.select_one(
        "[data-service-review-rating]"
    )
    if rating_el and rating_el.has_attr("data-rating"):
        return _safe_int(rating_el["data-rating"])
    if rating_el and rating_el.has_attr("data-service-review-rating"):
        return _safe_int(rating_el["data-service-review-rating"])

    # Fallback: look for star icons with an aria-label like "Rated 5 out of 5 stars"
    aria_el = card.select_one("[aria-label*='Rated']")
    if aria_el and aria_el.has_attr("aria-label"):
        text = aria_el["aria-label"]
        for token in text.split():
            maybe = _safe_int(token)
            if maybe is not None:
                return maybe
    return None

def _extract_review_id(card) -> Optional[str]:
    # Many review cards use an anchor with href containing the review ID.
    link = card.find("a", href=True)
    if not link:
        return None

    href = link["href"]
    parsed = urlparse(href)
    parts = [p for p in parsed.path.split("/") if p]
    if parts:
        return parts[-1]
    return href

def _parse_reviews_from_html(html: str) -> List[Review]:
    soup = BeautifulSoup(html, "html.parser")

    # Trustpilot typically wraps reviews in elements with data-service-review-id
    review_cards = soup.select("[data-service-review-id]") or soup.select(
        ".review-card"
    )

    reviews: List[Review] = []
    for card in review_cards:
        title_el = card.select_one("h2") or card.select_one(".review-title")
        title = title_el.get_text(strip=True) if title_el else None

        text_el = card.select_one("[data-review-text-typography]") or card.select_one(
            ".review-content__text"
        )
        text = text_el.get_text(strip=True) if text_el else None

        rating = _extract_rating_from_card(card)

        date_el = card.select_one("time")
        date_raw = date_el["datetime"] if date_el and date_el.has_attr("datetime") else (
            date_el.get_text(strip=True) if date_el else ""
        )
        date_obj = _parse_date_iso(date_raw) if date_raw else {"createdAt": None}

        consumer = _extract_consumer_from_card(card)
        review_id = card.get("data-service-review-id") or _extract_review_id(card)

        reviews.append(
            Review(
                id=review_id,
                text=text,
                title=title,
                rating=rating,
                date=date_obj,
                consumer=consumer,
            )
        )

    return reviews

def fetch_reviews(
    session: requests.Session,
    company_url: str,
    language: str,
    max_reviews: Optional[int],
    config: Dict[str, Any],
) -> List[Review]:
    """
    Fetch and parse reviews for a single company detail URL.

    This function uses the same requests.Session as the caller to ensure
    headers, proxies, and timeouts are consistent.
    """
    # Trustpilot encodes language via path segments, e.g. /en-GB/
    # We keep things simple: just reuse the provided URL while respecting language
    # if there is a locale segment.
    try:
        resp = session.get(company_url, params={"languages": language})
    except requests.RequestException as exc:
        logger.error("Failed to fetch reviews for %s: %s", company_url, exc)
        return []

    if not resp.ok:
        logger.warning(
            "Non-200 response while fetching reviews for %s: %s",
            company_url,
            resp.status_code,
        )
        return []

    reviews = _parse_reviews_from_html(resp.text)
    logger.info("Parsed %d reviews for %s", len(reviews), company_url)

    if max_reviews is not None and max_reviews >= 0:
        reviews = reviews[: max_reviews]

    return reviews