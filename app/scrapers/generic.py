from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0"}

def scrape_collection_generic(url: str):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    links = set()
    for a in soup.select("a[href]"):
        href = a.get("href")
        if not href:
            continue
        full = urljoin(url, href)
        if any(k in full.lower() for k in ["/product", "/products", "/p/"]):
            links.add(full.split("?")[0])
    return sorted(links)

def scrape_product_generic(url: str):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title = soup.find("h1")
    title = title.get_text(strip=True) if title else "Product"

    price = ""
    for sel in [".price", ".product-price", ".price-item--regular", ".price__regular .price-item"]:
        el = soup.select_one(sel)
        if el:
            price = el.get_text(strip=True)
            break

    imgs = []
    for img in soup.select("img"):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        if src.startswith("/"):
            src = urljoin(url, src)
        if src.startswith("http"):
            src = src.split("?")[0]
            imgs.append(src)
    images, seen = [], set()
    for u in imgs:
        if u not in seen:
            seen.add(u); images.append(u)

    desc_el = soup.select_one(".product-description, .description, #description, .tab-content, .product__description")
    description = desc_el.get_text(" ", strip=True) if desc_el else ""

    return {
        "url": url,
        "title": title,
        "price": price,
        "images": images[:12],
        "description": description,
        "options": {},
        "tags": [],
    }
