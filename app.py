"""
Copenhagen House Price Evaluator
Backend: Scrapes Dingeo.dk and Boliga.dk for property data,
then evaluates whether a listing is fairly priced.
"""

import re
import json
import time
import random
import logging
import os
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()  # loads variables from .env into os.environ

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Apify config ────────────────────────────────────────────────────────────
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
APIFY_BOLIGA_ACTOR = "shahidirfan~boliga-dk-scraper"
APIFY_RUN_URL = f"https://api.apify.com/v2/acts/{APIFY_BOLIGA_ACTOR}/run-sync-get-dataset-items"

# ─── Headers to mimic a real browser ────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ─── Copenhagen average price data (DKK/m²) by zip code ────────────────────
# Source: Boligsiden Markedsindeks + Finans Danmark, updated Q4 2025
# These serve as fallback when scraping fails and as baseline comparisons
CPH_AVG_PRICES = {
    # Apartments (lejlighed) - DKK per m²
    "apartment": {
        "1000": 58000, "1050": 58000, "1100": 55000, "1150": 56000,
        "1200": 57000, "1250": 58000, "1300": 55000, "1350": 54000,
        "1400": 53000, "1450": 52000, "1500": 50000, "1550": 48000,
        "1600": 47000, "1650": 46000, "1700": 45000, "1750": 44000,
        "1800": 43000, "1850": 44000, "1900": 45000, "1950": 46000,
        "2000": 52000,  # Frederiksberg
        "2100": 48000,  # København Ø
        "2200": 45000,  # København N
        "2300": 42000,  # København S
        "2400": 35000,  # København NV
        "2450": 40000,  # København SV
        "2500": 55000,  # Valby
        "2600": 38000,  # Glostrup
        "2610": 36000,  # Rødovre
        "2620": 33000,  # Albertslund
        "2625": 35000,  # Vallensbæk
        "2630": 34000,  # Taastrup
        "2635": 33000,  # Ishøj
        "2640": 32000,  # Hedehusene
        "2650": 38000,  # Hvidovre
        "2660": 36000,  # Brøndby Strand
        "2670": 37000,  # Greve
        "2680": 35000,  # Solrød Strand
        "2690": 34000,  # Karlslunde
        "2700": 40000,  # Brønshøj
        "2720": 42000,  # Vanløse
        "2730": 40000,  # Herlev
        "2740": 38000,  # Skovlunde
        "2750": 42000,  # Ballerup
        "2760": 38000,  # Måløv
        "2770": 36000,  # Kastrup
        "2791": 35000,  # Dragør
        "2800": 48000,  # Kongens Lyngby
        "2820": 45000,  # Gentofte
        "2830": 42000,  # Virum
        "2840": 50000,  # Holte
        "2850": 38000,  # Nærum
        "2860": 36000,  # Søborg
        "2870": 34000,  # Dyssegård
        "2880": 35000,  # Bagsværd
        "2900": 45000,  # Hellerup
        "2920": 42000,  # Charlottenlund
        "2930": 38000,  # Klampenborg
        "2942": 36000,  # Skodsborg
        "2950": 34000,  # Vedbæk
        "2960": 32000,  # Rungsted Kyst
        "2970": 30000,  # Hørsholm
        "2980": 28000,  # Kokkedal
        "2990": 26000,  # Nivå
        "3000": 28000,  # Helsingør
        "3050": 25000,  # Humlebæk
        "3060": 24000,  # Espergærde
        "3070": 22000,  # Snekkersten
        "3400": 20000,  # Hillerød
    },
    # Houses (villa/rækkehus) - DKK per m²
    "house": {
        "1000": 45000, "2000": 48000, "2100": 42000, "2200": 38000,
        "2300": 35000, "2400": 30000, "2450": 33000, "2500": 40000,
        "2600": 28000, "2610": 26000, "2620": 22000, "2625": 25000,
        "2630": 22000, "2635": 20000, "2640": 18000, "2650": 30000,
        "2660": 24000, "2670": 28000, "2680": 26000, "2690": 24000,
        "2700": 32000, "2720": 36000, "2730": 30000, "2740": 28000,
        "2750": 30000, "2760": 26000, "2770": 28000, "2791": 35000,
        "2800": 45000, "2820": 55000, "2830": 42000, "2840": 48000,
        "2850": 40000, "2860": 32000, "2870": 38000, "2880": 30000,
        "2900": 52000, "2920": 50000, "2930": 55000, "2942": 48000,
        "2950": 45000, "2960": 50000, "2970": 40000, "2980": 32000,
        "2990": 28000, "3000": 22000, "3050": 25000, "3060": 28000,
        "3070": 30000, "3400": 20000,
    },
}

# ─── Adjustment factors for multi-factor analysis ──────────────────────────
ENERGY_LABEL_FACTOR = {
    "A2020": 1.08, "A2015": 1.06, "A2010": 1.05, "A": 1.04,
    "B": 1.02, "C": 1.00, "D": 0.97, "E": 0.94, "F": 0.90, "G": 0.85,
}

BUILDING_AGE_FACTOR = {
    (2020, 2030): 1.05,
    (2010, 2019): 1.03,
    (2000, 2009): 1.01,
    (1990, 1999): 1.00,
    (1970, 1989): 0.97,
    (1950, 1969): 0.95,
    (1900, 1949): 0.98,  # charme-factor for old buildings
    (0, 1899): 1.00,     # historic buildings can be desirable
}

NOISE_FACTOR = {
    "low": 1.02,       # < 55 dB
    "moderate": 1.00,   # 55-65 dB
    "high": 0.96,       # 65-75 dB
    "very_high": 0.90,  # > 75 dB
}


def get_building_age_factor(year_built):
    """Get price adjustment factor based on building year."""
    if not year_built:
        return 1.0
    for (low, high), factor in BUILDING_AGE_FACTOR.items():
        if low <= year_built <= high:
            return factor
    return 1.0


# ─── Scraping Functions ─────────────────────────────────────────────────────

def scrape_dingeo(address: str) -> dict:
    """
    Attempt to scrape property details from Dingeo.dk for a given address.
    Returns: dict with energy_label, building_year, noise_level, etc.
    """
    result = {
        "energy_label": None,
        "building_year": None,
        "noise_level": None,
        "radon_risk": None,
        "flood_risk": None,
        "source": "dingeo.dk",
        "scraped": False,
    }

    try:
        # Dingeo URL format: /adresse/{postnr}-{by}/{vejnavn}-{nr}
        # We'll search first
        search_url = f"https://www.dingeo.dk/soeg/?q={requests.utils.quote(address)}"
        logger.info(f"Scraping Dingeo: {search_url}")

        resp = SESSION.get(search_url, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")

            # Try to find the address link in search results
            links = soup.select("a[href*='/adresse/']")
            if links:
                addr_url = links[0].get("href")
                if not addr_url.startswith("http"):
                    addr_url = f"https://www.dingeo.dk{addr_url}"

                time.sleep(random.uniform(1, 2))  # polite delay
                resp2 = SESSION.get(addr_url, timeout=15)

                if resp2.status_code == 200:
                    soup2 = BeautifulSoup(resp2.text, "lxml")
                    page_text = soup2.get_text()

                    # Extract energy label
                    energy_match = re.search(
                        r"[Ee]nergi(?:mærke|label)[:\s]*([A-G](?:2010|2015|2020)?)",
                        page_text
                    )
                    if energy_match:
                        result["energy_label"] = energy_match.group(1).upper()

                    # Extract building year
                    year_match = re.search(r"[Oo]pført[:\s]*(\d{4})", page_text)
                    if year_match:
                        result["building_year"] = int(year_match.group(1))

                    # Extract noise level
                    noise_match = re.search(r"(\d+)\s*dB", page_text)
                    if noise_match:
                        db = int(noise_match.group(1))
                        if db < 55:
                            result["noise_level"] = "low"
                        elif db < 65:
                            result["noise_level"] = "moderate"
                        elif db < 75:
                            result["noise_level"] = "high"
                        else:
                            result["noise_level"] = "very_high"

                    result["scraped"] = True

    except Exception as e:
        logger.warning(f"Dingeo scraping failed: {e}")

    return result


def scrape_boliga_sold(zip_code: str, property_type: str = "apartment") -> list:
    """
    Fetch recent sold prices from Boliga.dk via Apify (if token set),
    otherwise fall back to direct scraping.
    Returns: list of dicts with price, size_m2, price_per_m2, address, date, rooms
    """
    if APIFY_TOKEN:
        return _boliga_via_apify(zip_code, property_type)
    return _boliga_direct(zip_code, property_type)


def _boliga_via_apify(zip_code: str, property_type: str) -> list:
    """Call Apify Boliga scraper actor (async + poll) and return normalised sales list."""
    sales = []
    prop_type_map = {"apartment": "ejerlejlighed", "house": "villa"}
    boliga_type = prop_type_map.get(property_type, "ejerlejlighed")

    start_url = (
        f"https://www.boliga.dk/salg/resultater"
        f"?propertyType={boliga_type}"
        f"&zipCodes={zip_code}"
        f"&sort=date-d"
    )

    # Actor input — fetch 200 listings then filter by zip client-side
    payload = {
        "results_wanted": 200,
        "max_pages": 10,
        "proxyConfiguration": {"useApifyProxy": False},
    }

    try:
        # ── Step 1: Start the actor run (async) ──────────────────────────
        run_url = f"https://api.apify.com/v2/acts/{APIFY_BOLIGA_ACTOR}/runs"
        logger.info(f"Starting Apify Boliga actor for zip {zip_code}...")
        resp = requests.post(
            run_url,
            params={"token": APIFY_TOKEN},
            json=payload,
            timeout=30,
        )
        if not resp.ok:
            logger.warning(f"Apify start error {resp.status_code}: {resp.text[:300]}")
        resp.raise_for_status()

        run_data = resp.json()
        run_id = run_data["data"]["id"]
        dataset_id = run_data["data"]["defaultDatasetId"]
        logger.info(f"Apify run started: {run_id}")

        # ── Step 2: Poll until the run finishes ──────────────────────────
        status_url = f"https://api.apify.com/v2/actor-runs/{run_id}"
        for attempt in range(24):  # poll up to 2 minutes (24 × 5s)
            time.sleep(5)
            status_resp = requests.get(
                status_url,
                params={"token": APIFY_TOKEN},
                timeout=15,
            )
            try:
                resp_data = status_resp.json()
                # Debug: log the actual response structure on first attempt
                if attempt == 0:
                    logger.info(f"Status response keys: {list(resp_data.keys())}")
                    if "error" in resp_data:
                        logger.info(f"Status error: {resp_data['error']}")
                    if "data" in resp_data:
                        logger.info(f"Status data keys: {list(resp_data['data'].keys())}")

                status = resp_data.get("data", {}).get("status", "UNKNOWN")
                logger.info(f"Apify run status: {status} (attempt {attempt + 1})")
            except Exception as e:
                logger.warning(f"Failed to parse status response: {e}, response: {status_resp.text[:500]}")
                status = "UNKNOWN"

            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                break

        if status != "SUCCEEDED":
            logger.warning(f"Apify run ended with status: {status}")
            return sales

        # ── Step 3: Fetch results and filter by zip code ─────────────────
        dataset_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        items_resp = requests.get(
            dataset_url,
            params={"token": APIFY_TOKEN, "format": "json", "limit": 200},
            timeout=30,
        )
        if not items_resp.ok:
            logger.warning(f"Failed to fetch dataset: {items_resp.status_code} {items_resp.text[:300]}")
            return sales

        all_items = items_resp.json()
        if not isinstance(all_items, list):
            logger.warning(f"Dataset response not a list: {type(all_items)}")
            return sales
        logger.info(f"Apify returned {len(all_items)} total items")

        # Filter to requested zip code and map to our standard format
        zip_int = int(zip_code)
        zip_codes_in_results = set()

        for item in all_items:
            item_zip = int(item.get("zip_code", 0))
            zip_codes_in_results.add(item_zip)

            if item_zip != zip_int:
                continue

            price = item.get("price") or 0
            size  = item.get("size") or 0
            price_m2 = item.get("squaremeter_price") or (
                round(price / size) if price and size else 0
            )

            if price and size:
                sales.append({
                    "address": f"{item.get('street', '')} {zip_code} {item.get('city', '')}".strip()[:60],
                    "price": int(price),
                    "size_m2": int(size),
                    "price_per_m2": int(price_m2),
                    "rooms": item.get("rooms"),
                    "date": item.get("created_date", "")[:10],
                    "building_year": item.get("build_year"),
                })

        logger.info(f"Filtered to {len(sales)} listings for zip {zip_code}")
        logger.info(f"Zip codes in results: {sorted(zip_codes_in_results)[:20]}")

    except Exception as e:
        logger.warning(f"Apify Boliga call failed: {type(e).__name__}: {e}", exc_info=True)

    return sales


def _boliga_direct(zip_code: str, property_type: str) -> list:
    """Fallback: attempt direct scraping of Boliga (often blocked)."""
    sales = []
    try:
        prop_type_map = {"apartment": "ejerlejlighed", "house": "villa"}
        boliga_type = prop_type_map.get(property_type, "ejerlejlighed")
        url = (
            f"https://www.boliga.dk/salg/resultater"
            f"?propertyType={boliga_type}"
            f"&zipCodes={zip_code}"
            f"&sort=date-d&page=1"
        )
        logger.info(f"Direct scraping Boliga: {url}")
        resp = SESSION.get(url, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            scripts = soup.find_all("script", type="application/json")
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and "results" in data:
                        for item in data["results"]:
                            sales.append({
                                "address": item.get("address", ""),
                                "price": item.get("price", 0),
                                "size_m2": item.get("size", 0),
                                "price_per_m2": item.get("sqmPrice", 0),
                                "rooms": item.get("rooms", 0),
                                "date": item.get("soldDate", ""),
                                "building_year": item.get("buildYear", None),
                            })
                except (json.JSONDecodeError, TypeError):
                    continue
    except Exception as e:
        logger.warning(f"Direct Boliga scraping failed: {e}")
    return sales


def scrape_boligsiden_stats(zip_code: str) -> dict:
    """
    Attempt to scrape area statistics from Boligsiden.dk.
    Returns: dict with avg_price_m2, avg_days_on_market, avg_discount
    """
    stats = {
        "avg_price_m2": None,
        "avg_days_on_market": None,
        "avg_discount_pct": None,
        "source": "boligsiden.dk",
        "scraped": False,
    }

    try:
        url = f"https://www.boligsiden.dk/markedsindeks/{zip_code}"
        logger.info(f"Scraping Boligsiden: {url}")

        resp = SESSION.get(url, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            page_text = soup.get_text()

            # Try to extract key statistics
            price_match = re.search(r"([\d.]+)\s*kr\.?\s*/\s*m[²2]", page_text)
            if price_match:
                stats["avg_price_m2"] = int(price_match.group(1).replace(".", ""))

            days_match = re.search(r"(\d+)\s*dage", page_text)
            if days_match:
                stats["avg_days_on_market"] = int(days_match.group(1))

            discount_match = re.search(r"(-?\d+[,.]?\d*)\s*%", page_text)
            if discount_match:
                stats["avg_discount_pct"] = float(
                    discount_match.group(1).replace(",", ".")
                )

            stats["scraped"] = True

    except Exception as e:
        logger.warning(f"Boligsiden scraping failed: {e}")

    return stats


# ─── Analysis Engine ─────────────────────────────────────────────────────────

def analyze_price(
    asking_price: int,
    size_m2: int,
    zip_code: str,
    property_type: str = "apartment",
    energy_label: str = None,
    building_year: int = None,
    noise_level: str = None,
    rooms: int = None,
    comparable_sales: list = None,
) -> dict:
    """
    Full price analysis combining all three evaluation methods:
    1. Simple over/under (asking price vs area average)
    2. Price per m² comparison
    3. Multi-factor adjusted analysis
    """
    asking_price_m2 = round(asking_price / size_m2) if size_m2 > 0 else 0

    # ── 1. Get area average price ────────────────────────────────────────
    type_prices = CPH_AVG_PRICES.get(property_type, CPH_AVG_PRICES["apartment"])
    area_avg_m2 = type_prices.get(zip_code)

    # Try nearby zip codes if exact match not found
    if area_avg_m2 is None:
        zip_int = int(zip_code)
        for offset in [10, -10, 20, -20, 50, -50, 100, -100]:
            nearby = str(zip_int + offset)
            if nearby in type_prices:
                area_avg_m2 = type_prices[nearby]
                break

    if area_avg_m2 is None:
        area_avg_m2 = 40000  # fallback average for greater Copenhagen

    # ── 2. Use comparable sales if available ─────────────────────────────
    comp_avg_m2 = None
    comp_median_m2 = None
    comp_count = 0

    if comparable_sales:
        prices_m2 = [
            s["price_per_m2"] for s in comparable_sales
            if s.get("price_per_m2") and s["price_per_m2"] > 0
        ]
        if prices_m2:
            comp_avg_m2 = round(sum(prices_m2) / len(prices_m2))
            sorted_prices = sorted(prices_m2)
            mid = len(sorted_prices) // 2
            comp_median_m2 = sorted_prices[mid] if len(sorted_prices) % 2 else \
                round((sorted_prices[mid - 1] + sorted_prices[mid]) / 2)
            comp_count = len(prices_m2)

    # Use best available reference price
    reference_m2 = comp_avg_m2 if comp_avg_m2 else area_avg_m2

    # ── 3. Simple over/under ─────────────────────────────────────────────
    simple_diff_pct = round(((asking_price_m2 - reference_m2) / reference_m2) * 100, 1)
    if simple_diff_pct > 10:
        simple_verdict = "overpriced"
    elif simple_diff_pct < -10:
        simple_verdict = "underpriced"
    else:
        simple_verdict = "fairly_priced"

    # ── 4. Price per m² detailed comparison ──────────────────────────────
    m2_analysis = {
        "asking_price_m2": asking_price_m2,
        "area_avg_m2": area_avg_m2,
        "comp_avg_m2": comp_avg_m2,
        "comp_median_m2": comp_median_m2,
        "comp_count": comp_count,
        "diff_vs_area_pct": round(
            ((asking_price_m2 - area_avg_m2) / area_avg_m2) * 100, 1
        ),
        "diff_vs_comps_pct": round(
            ((asking_price_m2 - comp_avg_m2) / comp_avg_m2) * 100, 1
        ) if comp_avg_m2 else None,
    }

    # ── 5. Multi-factor adjusted fair price ──────────────────────────────
    adjusted_m2 = reference_m2

    adjustments = []

    # Energy label adjustment
    if energy_label and energy_label.upper() in ENERGY_LABEL_FACTOR:
        factor = ENERGY_LABEL_FACTOR[energy_label.upper()]
        adjusted_m2 *= factor
        adjustments.append({
            "factor": "Energy label",
            "value": energy_label.upper(),
            "adjustment_pct": round((factor - 1) * 100, 1),
        })

    # Building age adjustment
    if building_year:
        factor = get_building_age_factor(building_year)
        adjusted_m2 *= factor
        adjustments.append({
            "factor": "Building year",
            "value": str(building_year),
            "adjustment_pct": round((factor - 1) * 100, 1),
        })

    # Noise adjustment
    if noise_level and noise_level in NOISE_FACTOR:
        factor = NOISE_FACTOR[noise_level]
        adjusted_m2 *= factor
        adjustments.append({
            "factor": "Noise level",
            "value": noise_level,
            "adjustment_pct": round((factor - 1) * 100, 1),
        })

    adjusted_m2 = round(adjusted_m2)
    adjusted_fair_price = adjusted_m2 * size_m2
    multi_diff_pct = round(
        ((asking_price_m2 - adjusted_m2) / adjusted_m2) * 100, 1
    )

    if multi_diff_pct > 10:
        multi_verdict = "overpriced"
    elif multi_diff_pct < -10:
        multi_verdict = "underpriced"
    else:
        multi_verdict = "fairly_priced"

    # ── 6. Overall verdict ───────────────────────────────────────────────
    # Weighted average of the three methods
    verdicts = [simple_verdict, multi_verdict]
    overpriced_count = verdicts.count("overpriced")
    underpriced_count = verdicts.count("underpriced")

    if overpriced_count > underpriced_count:
        overall_verdict = "overpriced"
    elif underpriced_count > overpriced_count:
        overall_verdict = "underpriced"
    else:
        overall_verdict = "fairly_priced"

    # Confidence based on data availability
    confidence_score = 30  # base
    if comp_count >= 5:
        confidence_score += 30
    elif comp_count >= 2:
        confidence_score += 15
    if energy_label:
        confidence_score += 10
    if building_year:
        confidence_score += 10
    if noise_level:
        confidence_score += 10
    if comp_count >= 10:
        confidence_score += 10

    return {
        "overall": {
            "verdict": overall_verdict,
            "confidence_pct": min(confidence_score, 100),
            "asking_price": asking_price,
            "asking_price_m2": asking_price_m2,
            "estimated_fair_price": adjusted_fair_price,
            "estimated_fair_price_m2": adjusted_m2,
            "diff_pct": multi_diff_pct,
        },
        "simple": {
            "verdict": simple_verdict,
            "diff_pct": simple_diff_pct,
            "reference_m2": reference_m2,
        },
        "price_per_m2": m2_analysis,
        "multi_factor": {
            "verdict": multi_verdict,
            "adjusted_fair_m2": adjusted_m2,
            "adjusted_fair_price": adjusted_fair_price,
            "diff_pct": multi_diff_pct,
            "adjustments": adjustments,
        },
        "comparable_sales": (comparable_sales or [])[:10],
        "data_sources": {
            "area_average": f"Copenhagen zip {zip_code} baseline",
            "comparable_sales_count": comp_count,
        },
    }


# ─── API Routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/evaluate", methods=["POST"])
def evaluate():
    """Main evaluation endpoint."""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    address = data.get("address", "")
    asking_price = data.get("asking_price")
    size_m2 = data.get("size_m2")
    zip_code = data.get("zip_code", "")
    property_type = data.get("property_type", "apartment")
    energy_label = data.get("energy_label")
    building_year = data.get("building_year")
    noise_level = data.get("noise_level")
    rooms = data.get("rooms")

    if not asking_price or not size_m2 or not zip_code:
        return jsonify({
            "error": "Missing required fields: asking_price, size_m2, zip_code"
        }), 400

    # ── Step 1: Try scraping Dingeo for property details ─────────────────
    dingeo_data = {}
    if address:
        dingeo_data = scrape_dingeo(address)
        # Use scraped values as fallbacks
        if not energy_label and dingeo_data.get("energy_label"):
            energy_label = dingeo_data["energy_label"]
        if not building_year and dingeo_data.get("building_year"):
            building_year = dingeo_data["building_year"]
        if not noise_level and dingeo_data.get("noise_level"):
            noise_level = dingeo_data["noise_level"]

    # ── Step 2: Try scraping Boliga for comparable sales ─────────────────
    comparable_sales = scrape_boliga_sold(zip_code, property_type)

    # ── Step 3: Try scraping Boligsiden for area stats ───────────────────
    boligsiden_stats = scrape_boligsiden_stats(zip_code)

    # ── Step 4: Run analysis ─────────────────────────────────────────────
    result = analyze_price(
        asking_price=int(asking_price),
        size_m2=int(size_m2),
        zip_code=zip_code,
        property_type=property_type,
        energy_label=energy_label,
        building_year=int(building_year) if building_year else None,
        noise_level=noise_level,
        rooms=int(rooms) if rooms else None,
        comparable_sales=comparable_sales,
    )

    # Add scraping metadata
    result["scraping"] = {
        "dingeo": {
            "scraped": dingeo_data.get("scraped", False),
            "data": dingeo_data,
        },
        "boliga": {
            "comparable_sales_found": len(comparable_sales),
            "via_apify": bool(APIFY_TOKEN),
        },
        "boligsiden": boligsiden_stats,
    }

    return jsonify(result)


@app.route("/api/zip-codes", methods=["GET"])
def get_zip_codes():
    """Return available Copenhagen zip codes."""
    zips = sorted(set(
        list(CPH_AVG_PRICES["apartment"].keys()) +
        list(CPH_AVG_PRICES["house"].keys())
    ))
    return jsonify(zips)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
