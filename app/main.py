import io, re
from urllib.parse import urlparse
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
import pandas as pd

from app.shopify_utils import build_shopify_rows, normalize_images_and_positions
from app.scrapers.ansab_jahangir import scrape_collection_ansab, scrape_product_ansab
from app.scrapers.generic import scrape_collection_generic, scrape_product_generic

app = FastAPI(title="Shopify CSV Scraper (Web)")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

env = Environment(loader=FileSystemLoader("app/templates"), autoescape=select_autoescape())

# Health endpoints for Render
@app.get("/healthz")
@app.head("/healthz")
def healthz():
    return HTMLResponse("", status_code=200)

@app.head("/")
def head_root():
    return HTMLResponse("", status_code=200)

def collect_with_fallback(url: str, limit: int):
    which = "ansab" if "ansabjahangirstudio.com" in urlparse(url).netloc else "generic"
    if which == "ansab":
        urls = scrape_collection_ansab(url) or scrape_collection_generic(url)
    else:
        urls = scrape_collection_generic(url)
    if limit and len(urls) > limit:
        urls = urls[:limit]
    if not urls:
        urls = [url]
    return urls, which

def scrape_product_any(url: str, which: str):
    if which == "ansab":
        try:
            return scrape_product_ansab(url)
        except Exception:
            pass
    return scrape_product_generic(url)

@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    tpl = env.get_template("index.html")
    return HTMLResponse(tpl.render())

@app.post("/generate", response_class=HTMLResponse)
def generate(
    request: Request,
    collection_url: str = Form(...),
    limit_products: int = Form(0),
    vendor_default: str = Form(""),
    product_type_fallback: str = Form(""),
    product_category: str = Form(""),
    extra_tags: str = Form(""),
    option1_name: str = Form("Size"),
    published: bool = Form(True),
    add_seo: bool = Form(True),
    inventory_qty_default: int = Form(50),
    variant_inventory_tracker: str = Form("shopify"),
    variant_inventory_policy: str = Form("deny"),
    fulfillment_service: str = Form("manual"),
    requires_shipping: bool = Form(True),
    taxable: bool = Form(True),
    status: str = Form("Active"),
    image_strategy: str = Form("first_variant"),
    variant_image_strategy: str = Form("rotate"),
    add_metafields: bool = Form(False),
    meta_namespace: str = Form("custom"),
    meta_design_code: bool = Form(True),
    meta_fabric: bool = Form(True),
    meta_color: bool = Form(True),
    meta_work_details: bool = Form(True),
):
    urls, which = collect_with_fallback(collection_url, int(limit_products))

    scraped = []
    for u in urls:
        try:
            p = scrape_product_any(u, which)
            p["vendor"] = p.get("vendor") or vendor_default
            p["type"] = p.get("type") or product_type_fallback
            if product_category: p["product_category"] = product_category
            if extra_tags:
                t = p.get("tags") or []
                if isinstance(t, str): t = [t] if t else []
                t.extend([x.strip() for x in extra_tags.split(",") if x.strip()])
                p["tags"] = list(dict.fromkeys(t))
            scraped.append(p)
        except Exception:
            continue

    cfg = {
        "published": bool(published),
        "vendor_default": vendor_default,
        "product_category": product_category,
        "type_fallback": product_type_fallback,
        "extra_tags": extra_tags,
        "option1_name": option1_name,
        "variant_inventory_tracker": variant_inventory_tracker,
        "inventory_qty_default": int(inventory_qty_default),
        "variant_inventory_policy": variant_inventory_policy,
        "fulfillment_service": fulfillment_service,
        "requires_shipping": bool(requires_shipping),
        "taxable": bool(taxable),
        "seo_mode": ("auto" if bool(add_seo) else "custom"),
        "status": status,
        "force_single_variant": True,
        "image_alt_from_title": True,
        "image_strategy": image_strategy,
        "variant_image_strategy": variant_image_strategy,
    }
    rows = build_shopify_rows(scraped, cfg, price_field="price")
    df = pd.DataFrame(rows)
    df = normalize_images_and_positions(df, image_strategy=image_strategy, image_alt_from_title=True)

    if add_metafields:
        def norm_handle(t):
            h = re.sub(r'[^a-z0-9\-]+','-', (t or '').strip().lower().replace(' ','-'))
            return re.sub(r'-+','-', h).strip('-') or 'product'
        value_map = {}
        for pdat in scraped:
            h = norm_handle(pdat.get('handle') or pdat.get('title'))
            html = pdat.get('body_html') or pdat.get('description_html') or pdat.get('description') or ''
            def grab(label):
                m = re.search(rf"<strong>{label}:</strong>\s*([^<]+)", html, re.I)
                return (m.group(1).strip() if m else '')
            value_map[h] = {
                'design_code': grab('Design Code'),
                'fabric': grab('Fabric'),
                'color': grab('Color'),
                'work_details': grab('Work Details'),
            }
        selected = [label for label, flag in [
            ("Design Code", meta_design_code),
            ("Fabric", meta_fabric),
            ("Color", meta_color),
            ("Work Details", meta_work_details),
        ] if flag]
        for label in selected:
            key = label.lower().replace(' ', '_')
            col = f"{label} (product.metafields.{meta_namespace}.{key})"
            if col not in df.columns: df[col] = ''
            for h, idxs in df.groupby('Handle', sort=False).groups.items():
                first = list(idxs)[0]
                df.at[first, col] = value_map.get(h, {}).get(key, '')

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    return StreamingResponse(io.BytesIO(csv_bytes), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="shopify_products.csv"'})
