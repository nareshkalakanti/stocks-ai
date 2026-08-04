#!/usr/bin/env python3
"""Scrape About Us / company profile text from a corporate website.

Usage (from repo root):
  python scripts/scrape_company_about.py --url https://www.hindalco.com/
  python scripts/scrape_company_about.py --ticker HINDALCO --market NSE
  python scripts/scrape_company_about.py --ticker HINDALCO --save
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stocks.core.database import load_company_profiles_from_db, save_company_profiles
from stocks.core.text_utils import safe_str
from stocks.market.website_about import scrape_about_for_ticker, scrape_website_about


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Corporate website URL")
    parser.add_argument("--ticker", help="NSE/BSE ticker; resolves website from DB/screener/Yahoo")
    parser.add_argument("--market", default="NSE", help="Market for ticker lookup (default NSE)")
    parser.add_argument(
        "--save",
        action="store_true",
        help="When --ticker is set and scrape passes, save long_description to company_profile_cache",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON result")
    args = parser.parse_args()

    if not args.url and not args.ticker:
        parser.error("Provide --url or --ticker")

    if args.url:
        result = scrape_website_about(args.url)
    else:
        result = scrape_about_for_ticker(args.ticker, args.market)

    if args.json:
        print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    else:
        status = "OK" if result.ok else "FAIL"
        print(f"[{status}] score={result.score} kind={result.page_kind or '—'} url={result.source_url or '—'}")
        if result.error:
            print(f"error: {result.error}")
        if result.validation:
            v = result.validation
            print(
                f"validation: words={v.words} chars={v.chars} "
                f"business_hits={v.business_hits} reasons={v.reasons or '[]'}"
            )
        if result.theme_tags:
            print(f"themes: {result.theme_tags}")
        if result.end_markets:
            print(f"end markets: {result.end_markets}")
        if result.products:
            print(f"products: {result.products[:300]}{'…' if len(result.products) > 300 else ''}")
        if result.ir_url:
            print(f"IR: {result.ir_url}")
        if result.candidates_tried:
            print("tried:", " → ".join(result.candidates_tried))
        if result.text:
            print()
            print(result.text)

    if args.save and args.ticker and result.ok and (result.text or result.has_investment_fields):
        ticker = safe_str(args.ticker).upper()
        stored = load_company_profiles_from_db([ticker]).get(ticker) or {}
        save_company_profiles(
            [
                {
                    "ticker": ticker,
                    "market": args.market or stored.get("market"),
                    "source": "website_about",
                    "website": stored.get("website") or result.source_url,
                    "long_description": result.text or stored.get("long_description"),
                    "company_sector": stored.get("company_sector"),
                    "company_industry": stored.get("company_industry"),
                    "headquarters": stored.get("headquarters"),
                    "employees": stored.get("employees"),
                    "products": result.products or stored.get("products"),
                    "end_markets": result.end_markets or stored.get("end_markets"),
                    "ir_url": result.ir_url or stored.get("ir_url"),
                    "theme_tags": result.theme_tags or stored.get("theme_tags"),
                }
            ]
        )
        print(f"\nsaved about for {ticker} → company_profile_cache", file=sys.stderr)

    sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
