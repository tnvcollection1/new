import re, json
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0"}

def _get_html(url, headers=None):
    r = requests.get(url, headers=headers or HEADERS, timeout=45)
    r.raise_for_status()
    return r.text

def _abs(base, href):
    if not href: return ""
    href = href.strip()
    if href.startswith("#"): return ""
    full = urljoin(base, href)
    full = full.split("?")[0].split("#")[0]
    if urlparse(full).netloc != urlparse(base).netloc:
        return ""
    return full

def _candidate_root(soup):
    for sel in ["main", "#main", ".main-content", ".page-main", ".content", ".container", ".product-grid", ".products-grid", "body"]:
        el = soup.select_one(sel)
        if el: return el
    return soup

def _is_probable_product(u):
    try:
        html = _get_html(u)
        s = BeautifulSoup(html, "html.parser")
        if s.find("meta", {"property":"og:type", "content":"product"}):
            return True
        if s.select_one(".sku, .product-sku, [itemprop='sku']"):
            return True
        if s.find("h1") and s.find(string=re.compile(r"\bSKU\b", re.I)):
            return True
        return False
    except Exception:
        return False

def _filter_product_images(url, soup):
    candidates = []
    selectors = [
        "[data-zoom-image]",
        "[data-large-image]",
        "[data-image]",
        "a.cloud-zoom-gallery",
        ".product-essential .gallery img",
        ".product-media img",
        ".picture img",
        ".gallery img",
        "img",
        "[style*='background-image']",
    ]
    for sel in selectors:
        for el in soup.select(sel):
            src = el.get("data-zoom-image") or el.get("data-large-image") or el.get("data-image") or el.get("href") or el.get("src") or el.get("data-src") or ""
            if not src and el.has_attr("style"):
                m = re.search(r"background-image\s*:\s*url\((['\"]?)(.*?)\1\)", el.get("style",""), re.I)
                if m: src = m.group(2)
            full = _abs(url, src)
            if not full: 
                continue
            low = full.lower()
            if any(bad in low for bad in ["/themes/", ".svg", "logo", "icon"]):
                continue
            if not low.endswith((".jpg",".jpeg",".png",".webp")):
                continue
            candidates.append(full)
    for m in soup.select('meta[property="og:image"], meta[name="og:image"]'):
        src = (m.get("content") or "").strip()
        full = _abs(url, src)
        if full: candidates.append(full)
    ordered, seen = [], set()
    for u in candidates:
        if u not in seen:
            seen.add(u); ordered.append(u)
    return ordered[:20]

def scrape_collection_ansab(collection_url: str):
    html = _get_html(collection_url)
    soup = BeautifulSoup(html, "html.parser")
    root = _candidate_root(soup)

    links = set()
    for a in root.select("a[href]"):
        full = _abs(collection_url, a.get("href"))
        if not full:
            continue
        text = (a.get_text(" ", strip=True) or "").lower()
        path = urlparse(full).path.strip("/")
        if not path or path == urlparse(collection_url).path.strip("/"):
            continue
        if "view detail" in text:
            links.add(full); continue
        if "/" not in path and path not in {"formals","bridals","pret","luxe-pret","digital-silk","chikan","kids","menswear","basics"}:
            links.add(full); continue
        low = full.lower()
        if any(k in low for k in ("/product","/products/","/p/")):
            links.add(full)
    return [u for u in sorted(links) if _is_probable_product(u)]

def _clean_price(text):
    if not text: return ""
    return re.sub(r"[^\d.]", "", text.replace(",", ""))

def _grab_text_after_heading(soup, heading_regex):
    h = soup.find(lambda tag: tag.name in ("h2","h3","h4") and heading_regex.search(tag.get_text(" ", strip=True)))
    if not h:
        return ""
    parts = []
    for sib in h.next_siblings:
        nm = getattr(sib, "name", "") or ""
        if nm.lower() in ("h2","h3","h4"):
            break
        if hasattr(sib, "get_text"):
            txt = sib.get_text(" ", strip=True)
        else:
            txt = str(sib).strip()
        if txt:
            parts.append(txt)
    return "\n\n".join(parts).strip()

def scrape_product_ansab(url: str):
    html = _get_html(url)
    s = BeautifulSoup(html, "html.parser")
    product_scope = s.select_one(".product-details, .product-essential, .product-page, .product-details-page") or s

    title = ""
    og = s.find("meta", {"property":"og:title"}) or s.find("meta", {"name":"og:title"})
    if og and og.get("content"): title = og["content"].strip()
    if not title:
        h1 = product_scope.find("h1") or s.find("h1")
        title = h1.get_text(strip=True) if h1 else "Product"

    scope_txt = product_scope.get_text("\n", strip=True)
    attrs = {}
    for key in ("Design Code", "Color", "Fabric", "Work Details"):
        m = re.search(rf"{key}\s*:\s*([^\n\r]+)", scope_txt, re.IGNORECASE)
        if m: attrs[key] = m.group(1).strip()

    price = sale_price = compare_at = ""
    for script in s.find_all("script", {"type":"application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        for d in (data if isinstance(data, list) else [data]):
            if isinstance(d, dict) and d.get("@type") == "Product":
                offers = d.get("offers") or {}
                if isinstance(offers, dict):
                    price = offers.get("price") or price
                elif isinstance(offers, list):
                    for off in offers:
                        price = off.get("price") or price
    if not price:
        for sel in [".price-value",".product-price .price-value",".price",".product-price",".price-item--regular",".price__regular .price-item"]:
            el = product_scope.select_one(sel) or s.select_one(sel)
            if el:
                price = _clean_price(el.get_text(strip=True)); break
    old = product_scope.select_one(".old-product-price, .price-old, .compare-at-price") or s.select_one(".compare-at-price")
    if old: compare_at = _clean_price(old.get_text(strip=True))
    special = product_scope.select_one(".special-price, .price-new, .product-price .price-new") or s.select_one(".price-new")
    if special: sale_price = _clean_price(special.get_text(strip=True))

    images = _filter_product_images(url, s)

    def grab_section(label_regex):
        return _grab_text_after_heading(product_scope, label_regex)

    product_details = grab_section(re.compile(r"^Product Details$", re.I))
    delivery = grab_section(re.compile(r"^DELIVERY\s*TIME$", re.I))
    care = grab_section(re.compile(r"^Care Instructions$", re.I))
    disclaimer = grab_section(re.compile(r"^Disclaimer$", re.I))

    html_parts = []
    if attrs.get("Design Code"): html_parts.append(f"<p><strong>Design Code:</strong> {attrs['Design Code']}</p>")
    if attrs.get("Color"): html_parts.append(f"<p><strong>Color:</strong> {attrs['Color']}</p>")
    if attrs.get("Fabric"): html_parts.append(f"<p><strong>Fabric:</strong> {attrs['Fabric']}</p>")
    if attrs.get("Work Details"): html_parts.append(f"<p><strong>Work Details:</strong> {attrs['Work Details']}</p>")
    if product_details: html_parts.append(f"<h3>Product Details</h3><p>{product_details}</p>")
    if delivery: html_parts.append(f"<h3>Delivery Time</h3><p>{delivery}</p>")
    if care: html_parts.append(f"<h3>Care Instructions</h3><p>{care}</p>")
    if disclaimer: html_parts.append(f"<h3>Disclaimer</h3><p>{disclaimer}</p>")
    body_html = "\n".join(html_parts).strip()

    sizes = []
    sel = product_scope.find("select", attrs={"name": lambda v: v and "size" in v.lower()}) or product_scope.find("select", id=re.compile("size", re.I))
    if sel:
        for opt in sel.select("option"):
            val = opt.get_text(" ", strip=True)
            if val and "select" not in val.lower():
                sizes.append(val)
    for btn in product_scope.select("button, .swatch-element, .variant-option, .sizes li, .option-list li"):
        t = btn.get_text(" ", strip=True)
        tl = t.lower()
        if t and any(x in tl.split() for x in ["xs","s","m","l","xl","xxl","custom","order"]):
            if t not in sizes:
                sizes.append(t)

    sku = ""
    sku_el = product_scope.select_one(".sku, .product-sku, .sku-number, [itemprop='sku']") or s.select_one("[itemprop='sku']")
    if sku_el: sku = sku_el.get_text(strip=True)
    if not sku and attrs.get("Design Code"):
        sku = attrs["Design Code"]

    tags = []
    for bc in s.select(".breadcrumb a, nav.breadcrumb a"):
        txt = bc.get_text(" ", strip=True)
        if txt and txt.lower() != "home" and txt not in tags:
            tags.append(txt)

    sku_map = {}
    base = sku or "SKU"
    for sz in sizes:
        import re as _re
        norm = _re.sub(r"[^A-Z0-9]+", "-", sz.strip().upper())
        sku_map[sz] = f"{base}-{norm}" if base else norm

    return {
        "url": url,
        "title": title,
        "price": price,
        "sale_price": sale_price,
        "compare_at_price": compare_at,
        "images": images,
        "body_html": body_html,
        "description": product_details or "",
        "options": {"Size": sizes} if sizes else {},
        "sku": sku,
        "sku_map": sku_map,
        "tags": tags,
        "type": (tags[-1] if tags else ""),
    }
