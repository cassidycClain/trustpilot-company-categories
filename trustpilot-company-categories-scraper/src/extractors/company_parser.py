from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:  # Relative import when run as package
    from .review_parser import Review, fetch_reviews
except ImportError:  # Fallback when imports are absolute
    from review_parser import Review, fetch_reviews  # type: ignore

logger = logging.getLogger("trustpilot_scraper.company")

@dataclass
class Company:
    ID: str
    domain: Optional[str] = None
    ratingValue: Optional[float] = None
    reviewCount: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    country: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    zipCode: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    categoriesID: List[str] = field(default_factory=list)
    lastReviews: List[Review] = field(default_factory=list)
    reviews: List[Review] = field(default_factory=list)
    rating: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)
    similarBusinessUnits: List[Dict[str, Any]] = field(default_factory=list)
    aiSummary: Dict[str, Any] = field(default_factory=dict)
    sourceUrl: Optional[str] = None

def _create_session(config: Dict[str, Any]) -> requests.Session:
    session = requests.Session()
    headers = config.get("headers") or {}
    if "User-Agent" not in headers:
        headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; TrustpilotScraper/1.0; +https://bitbash.dev)"
        )
    session.headers.update(headers)

    proxies = config.get("proxies") or None
    if proxies:
        session.proxies.update(proxies)

    timeout = config.get("timeoutSeconds", 15)
    session.request = _wrap_request_with_timeout(session.request, timeout)  # type: ignore

    return session

def _wrap_request_with_timeout(fn, timeout: int):
    def wrapped(method, url, **kwargs):
        if "timeout" not in kwargs:
            kwargs["timeout"] = timeout
        return fn(method, url, **kwargs)

    return wrapped

def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None

def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def _extract_domain(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.netloc or None

def _company_from_ld_json(
    data: Dict[str, Any],
    base_url: str,
    categories_id_hint: Optional[str] = None,
) -> Optional[Company]:
    if not isinstance(data, dict):
        return None

    at_type = data.get("@type")
    if isinstance(at_type, list):
        types = [t.lower() for t in at_type]
    elif isinstance(at_type, str):
        types = [at_type.lower()]
    else:
        types = []

    if not any(t in ("organization", "localbusiness") for t in types):
        # Not a business object
        return None

    url = data.get("url") or data.get("@id") or None
    if url and url.startswith("/"):
        url = urljoin(base_url, url)

    agg = data.get("aggregateRating") or {}
    rating_value = _safe_float(agg.get("ratingValue"))
    review_count = _safe_int(agg.get("reviewCount"))

    address_data = data.get("address") or {}
    if isinstance(address_data, list) and address_data:
        address_data = address_data[0]
    if not isinstance(address_data, dict):
        address_data = {}

    postal = address_data.get("postalCode") or None
    city = address_data.get("addressLocality") or None
    country = address_data.get("addressCountry") or None
    street = address_data.get("streetAddress") or None

    website_url = None
    same_as = data.get("sameAs")
    if isinstance(same_as, list):
        # Try to find the first non-Trustpilot URL as the website
        for entry in same_as:
            if isinstance(entry, str) and "trustpilot" not in entry:
                website_url = entry
                break
    elif isinstance(same_as, str):
        website_url = same_as

    domain = _extract_domain(website_url or url)

    company = Company(
        ID=data.get("@id") or (domain or url or ""),
        domain=domain,
        ratingValue=rating_value,
        reviewCount=review_count,
        name=data.get("name"),
        description=data.get("description"),
        image=data.get("image"),
        country=country,
        address=street,
        city=city,
        zipCode=postal,
        website=website_url,
        email=None,  # Trustpilot usually does not expose emails directly
        phone=data.get("telephone"),
        categories=[],
        categoriesID=[categories_id_hint] if categories_id_hint else [],
        rating={
            "bestRating": str(agg.get("bestRating") or "5"),
            "worstRating": str(agg.get("worstRating") or "1"),
            "ratingValue": str(rating_value) if rating_value is not None else None,
            "reviewCount": str(review_count) if review_count is not None else None,
        },
        data={
            # Without granular histogram we only reflect total review count
            "one": 0,
            "two": 0,
            "three": 0,
            "four": 0,
            "five": 0,
            "total": review_count or 0,
        },
        similarBusinessUnits=[],
        aiSummary={},
        sourceUrl=url,
    )

    # Derive simple category names if present
    category = data.get("category") or data.get("keywords")
    if isinstance(category, list):
        company.categories = [str(c) for c in category]
    elif isinstance(category, str):
        company.categories = [category]

    # Basic AI-style text summary (no external API)
    company.aiSummary = _build_ai_summary(company)

    return company

def _build_ai_summary(company: Company) -> Dict[str, Any]:
    # Lightweight, deterministic text summary based on available fields
    parts = []
    if company.name:
        parts.append(f"{company.name} is a business listed on Trustpilot")
    else:
        parts.append("This business is listed on Trustpilot")

    if company.categories:
        parts.append(
            f"operating in the {', '.join(sorted(set(company.categories)))} sector"
        )

    if company.country:
        location_bits = [company.city, company.country]
        loc = ", ".join([b for b in location_bits if b])
        if loc:
            parts.append(f"and appears to be based in {loc}")

    if company.ratingValue is not None and company.reviewCount is not None:
        parts.append(
            f"with an average rating of {company.ratingValue:.1f} from "
            f"{company.reviewCount} reviews"
        )
    elif company.ratingValue is not None:
        parts.append(f"and an average rating of {company.ratingValue:.1f}")

    summary = ", ".join(parts).strip()
    if summary and not summary.endswith("."):
        summary += "."

    return {
        "summary": summary,
        "status": "success",
        "lang": "en",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }

def _parse_ld_json_blocks(
    html: str,
    base_url: str,
    categories_id_hint: Optional[str] = None,
) -> List[Company]:
    soup = BeautifulSoup(html, "html.parser")
    companies: List[Company] = []
    seen_ids: set[str] = set()

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.text
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        items: Iterable[Any]
        if isinstance(data, list):
            items = data
        else:
            items = (data,)

        for item in items:
            if not isinstance(item, dict):
                continue
            company = _company_from_ld_json(
                item, base_url=base_url, categories_id_hint=categories_id_hint
            )
            if company and company.ID not in seen_ids:
                seen_ids.add(company.ID)
                companies.append(company)

    return companies

def _fetch_page(
    session: requests.Session, url: str
) -> Optional[str]:
    try:
        logger.debug("Fetching URL: %s", url)
        resp = session.get(url)
        if not resp.ok:
            logger.warning("Non-200 response from %s: %s", url, resp.status_code)
            return None
        return resp.text
    except requests.RequestException as exc:
        logger.error("Request error for %s: %s", url, exc)
        return None

def _attach_reviews_to_companies(
    session: requests.Session,
    companies: List[Company],
    config: Dict[str, Any],
    params: Dict[str, Any],
) -> None:
    include_reviews = bool(params.get("includeReviews"))
    if not include_reviews:
        return

    max_reviews = params.get("maxReviewsPerCompany")
    language = params.get("language") or config.get("defaultLanguage", "en")

    for company in companies:
        if not company.sourceUrl:
            continue
        try:
            reviews = fetch_reviews(
                session=session,
                company_url=company.sourceUrl,
                language=language,
                max_reviews=max_reviews,
                config=config,
            )
        except Exception as exc:
            logger.error(
                "Failed fetching reviews for %s: %s", company.sourceUrl, exc
            )
            continue

        company.reviews = reviews
        # lastReviews is the most recent subset
        company.lastReviews = reviews[:3] if reviews else []

def _limit_pages(params: Dict[str, Any], config: Dict[str, Any]) -> int:
    if params.get("allPages"):
        # Respect a global safety cap from config to avoid unbounded scraping
        return int(config.get("maxPages", 5))
    return int(params.get("pages", 1) or 1)

def _search_by_category(
    session: requests.Session,
    base_url: str,
    params: Dict[str, Any],
    config: Dict[str, Any],
) -> List[Company]:
    category_id = params.get("categoryId")
    if not category_id:
        raise ValueError('For searchType="category" you must provide "categoryId".')

    pages_to_fetch = _limit_pages(params, config)
    companies: List[Company] = []

    for page in range(1, pages_to_fetch + 1):
        url = f"{base_url}/categories/{category_id}?page={page}"
        html = _fetch_page(session, url)
        if not html:
            continue
        batch = _parse_ld_json_blocks(
            html, base_url=base_url, categories_id_hint=str(category_id)
        )
        logger.info("Category page %d yielded %d companies.", page, len(batch))
        companies.extend(batch)

    _attach_reviews_to_companies(session, companies, config, params)
    return companies

def _search_by_keyword(
    session: requests.Session,
    base_url: str,
    params: Dict[str, Any],
    config: Dict[str, Any],
) -> List[Company]:
    keyword = params.get("keyword")
    if not keyword:
        raise ValueError('For searchType="keyword" you must provide "keyword".')

    pages_to_fetch = _limit_pages(params, config)
    companies: List[Company] = []

    for page in range(1, pages_to_fetch + 1):
        url = f"{base_url}/search?query={keyword}&page={page}"
        html = _fetch_page(session, url)
        if not html:
            continue
        batch = _parse_ld_json_blocks(html, base_url=base_url)
        logger.info("Search page %d yielded %d companies.", page, len(batch))
        companies.extend(batch)

    _attach_reviews_to_companies(session, companies, config, params)
    return companies

def _search_detail(
    session: requests.Session,
    base_url: str,
    params: Dict[str, Any],
    config: Dict[str, Any],
) -> List[Company]:
    domain = params.get("domain")
    if not domain:
        raise ValueError('For searchType="detail" you must provide "domain".')

    # Trustpilot typically uses /review/<domain>
    url = f"{base_url}/review/{domain}"
    html = _fetch_page(session, url)
    if not html:
        return []

    companies = _parse_ld_json_blocks(html, base_url=base_url)
    if not companies:
        logger.warning("No company metadata found for domain %s", domain)
        return []

    _attach_reviews_to_companies(session, companies, config, params)
    return companies

def search_companies(
    params: Dict[str, Any],
    config: Dict[str, Any],
) -> List[Company]:
    """
    Entry point for the rest of the application.

    The `params` argument is typically loaded from input.sample.json and should
    contain keys like:
      - searchType: "category" | "keyword" | "detail"
      - categoryId / keyword / domain (depending on searchType)
      - allPages: bool
      - includeReviews: bool
      - maxReviewsPerCompany: int
      - language: "en" | "de" | "fr" | ...
    """
    base_url = config.get("baseUrl", "https://www.trustpilot.com").rstrip("/")
    session = _create_session(config)

    search_type = (params.get("searchType") or "category").lower()
    logger.info("Starting search with type '%s'.", search_type)

    if search_type == "category":
        companies = _search_by_category(session, base_url, params, config)
    elif search_type == "keyword":
        companies = _search_by_keyword(session, base_url, params, config)
    elif search_type == "detail":
        companies = _search_detail(session, base_url, params, config)
    else:
        raise ValueError(f"Unsupported searchType: {search_type}")

    # Remove duplicates by ID while keeping first occurrence
    unique: Dict[str, Company] = {}
    for company in companies:
        if not company.ID:
            # Fall back to domain if ID is missing
            key = company.domain or company.sourceUrl or ""
        else:
            key = company.ID
        if key and key not in unique:
            unique[key] = company

    logger.info("Search completed, %d unique companies collected.", len(unique))
    return list(unique.values())