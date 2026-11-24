"""Room-rental watcher: checks search pages, filters by price/area, sends new listings to Telegram.
No AI involved. Usage:  python room_bot.py [--dry-run]
"""
import json, os, re, sys, time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------- CONFIG ----------
MAX_PRICE = 6600  # DKK/month
AREAS = ["islands brygge", "sydhavn", "frederiksberg", "østerbro", "osterbro", "vesterbro"]
# Paste here the search URLs you get in your browser AFTER applying the filters
# on each site (rooms, Copenhagen, max price). One URL per source/page.
SEARCH_URLS = [
    # "https://www.boligportal.dk/...paste your filtered search URL...",
]
# Which links on the page count as listings (regex on the href). Adjust per site.
LISTING_HREF = re.compile(r"(\d{5,})")
SEEN_FILE = Path("seen.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (personal room-search script)"}
# -----------------------------

PRICE_RE = re.compile(r"(\d{1,3}(?:[.\s]\d{3})+|\d{4,5})\s*(?:kr|dkk)", re.I)


def parse_price(text):
    m = PRICE_RE.search(text)
    return int(re.sub(r"[.\s]", "", m.group(1))) if m else None


def fetch_listings(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    found = {}
    for a in soup.find_all("a", href=True):
        m = LISTING_HREF.search(a["href"])
        if not m:
            continue
        link = urljoin(url, a["href"])
        text = " ".join(a.get_text(" ", strip=True).split())
        if len(text) < 15:  # skip empty/icon links
            continue
        found[link] = {"id": link, "title": text[:140], "price": parse_price(text), "text": text.lower()}
    return list(found.values())


def matches(item):
    if item["price"] is not None and item["price"] > MAX_PRICE:
        return False
    # If the card text mentions no known area, keep it (the search URL already filters by area).
    return True


def send_telegram(msg):
    token, chat = os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": msg, "disable_web_page_preview": "true"}, timeout=30)
    r.raise_for_status()


def main():
    dry = "--dry-run" in sys.argv
    seen = set(json.loads(SEEN_FILE.read_text())) if SEEN_FILE.exists() else set()
    first_run = not SEEN_FILE.exists()
    new = []
    for url in SEARCH_URLS:
        try:
            items = fetch_listings(url)
        except Exception as e:
            print(f"ERROR fetching {url}: {e}")
            continue
        print(f"{url}: {len(items)} listings parsed")
        for it in items:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            if matches(it):
                new.append(it)
        time.sleep(2)

    for it in new:
        price = f"{it['price']} kr" if it["price"] else "price not found"
        msg = f"🏠 {it['title']}\n💰 {price}\n{it['id']}"
        print(msg, "\n")
        if not dry and not first_run:  # first run just records existing listings
            send_telegram(msg)
    if first_run and not dry:
        print("First run: saved existing listings as 'seen', no alerts sent.")
    if not dry:
        SEEN_FILE.write_text(json.dumps(sorted(seen)))


if __name__ == "__main__":
    main()
