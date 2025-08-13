import io, re
import pandas as pd

SHOPIFY_COLUMNS = [
    "Handle","Title","Body (HTML)","Vendor","Product Category","Type","Tags","Published",
    "Option1 Name","Option1 Value",
    "Variant SKU","Variant Grams","Variant Inventory Tracker","Variant Inventory Qty",
    "Variant Inventory Policy","Variant Fulfillment Service","Variant Price","Variant Compare At Price",
    "Variant Requires Shipping","Variant Taxable","Variant Barcode",
    "Variant Image",
    "Image Src","Image Position","Image Alt Text","Gift Card","SEO Title","SEO Description","Status"
]

def _normalize_handle(title):
    title = str(title or "")
    handle = title.strip().lower().replace(" ", "-")
    handle = re.sub(r"[^a-z0-9\-]+", "-", handle)
    handle = re.sub(r"-+", "-", handle).strip("-")
    return handle or "product"

def _first_nonempty(*vals):
    for v in vals:
        if v:
            return v
    return ""

def _filter_images_impl(imgs):
    out, seen = [], set()
    for u in imgs or []:
        if not u: 
            continue
        s = str(u).strip()
        if not s:
            continue
        low = s.lower()
        if any(x in low for x in ["/themes/","/content/images/","logo",".svg","whats2","magnifying-glass","003-user","002-bag","icon"]):
            continue
        if not low.endswith((".jpg",".jpeg",".png",".webp")):
            continue
        s = re.split(r"[?#]", s)[0]
        if s not in seen:
            seen.add(s); out.append(s)
    return out

def _images_from_html(html):
    if not html:
        return []
    urls = re.findall(r'https?://[^\s"\'<>]+', html)
    return _filter_images_impl(urls)

def _filter_images(imgs):
    return _filter_images_impl(imgs)

def _strip_query(u: str) -> str:
    return re.split(r"[?#]", str(u or "").strip())[0]

def _filename(u: str) -> str:
    u = _strip_query(u)
    m = re.search(r"/([^/]+)$", u)
    return m.group(1) if m else u

def _stem_and_ext(name: str):
    m = re.match(r"^(.*?)(\.[A-Za-z0-9]+)$", name)
    return (m.group(1), m.group(2)) if m else (name, "")

def _angle_key(u: str) -> str:
    # Keep different angles, drop resized dupes only.
    name = _filename(u).lower()
    stem, ext = _stem_and_ext(name)
    stem = re.sub(r"[-_](?:\d{3,4}|\d{2,4}x\d{2,4}|[12]x|small|medium|large|thumbnail|thumb|tiny|mini|micro)$", "", stem)
    stem = re.sub(r"_(?:\d{2,4})x(?:\d{2,4})$", "", stem)
    stem = re.sub(r"[-_]+", "_", stem).strip("_-")
    # Ansab hint: if starts with a long numeric id, use it as the angle key
    m = re.match(r"^(\d{4,})[_-]", stem)
    if m:
        return m.group(1) + ext
    return stem + ext

def _valid_img(url: str) -> bool:
    if not url: return False
    u = str(url).strip().lower()
    if not u: return False
    if any(x in u for x in ["/themes/","/content/images/","logo",".svg","whats2","magnifying-glass","003-user","002-bag","icon"]):
        return False
    return u.endswith((".jpg",".jpeg",".png",".webp"))

def _angles_from(images, body_html=""):
    urls = list(images or [])
    if not urls and body_html:
        urls = _images_from_html(body_html)
    out, seen = [], set()
    for u in urls:
        if not _valid_img(u): continue
        u0 = _strip_query(u)
        key = _angle_key(u0)
        if key not in seen:
            seen.add(key); out.append(u0)
    return out

def build_shopify_rows(products, cfg, price_field="price"):
    rows = []
    published_str = "TRUE" if cfg.get("published", True) else "FALSE"

    vendor_default = cfg.get("vendor_default","")
    product_category = cfg.get("product_category","")
    type_fallback = cfg.get("type_fallback","")
    extra_tags = [t.strip() for t in (cfg.get("extra_tags","") or "").split(",") if t.strip()]
    option1_name = cfg.get("option1_name","Size")
    inv_tracker = cfg.get("variant_inventory_tracker","")
    inv_qty_default = cfg.get("inventory_qty_default", 0)
    inv_policy = cfg.get("variant_inventory_policy","deny")
    fulfill_service = cfg.get("fulfillment_service","manual")
    requires_shipping = "TRUE" if cfg.get("requires_shipping", True) else "FALSE"
    taxable = "TRUE" if cfg.get("taxable", True) else "FALSE"
    seo_mode = ("custom" if (cfg.get("seo_mode","auto") or "").lower()=="custom" else "auto")
    seo_title_default = cfg.get("seo_title_default","")
    seo_desc_default = cfg.get("seo_desc_default","")
    status = cfg.get("status","Active")
    force_single_variant = cfg.get("force_single_variant", True)
    image_alt_from_title = cfg.get("image_alt_from_title", True)
    image_strategy = (cfg.get("image_strategy") or "first_variant").lower()
    variant_image_strategy = (cfg.get("variant_image_strategy") or "rotate").lower()  # rotate | none

    for p in products:
        title = p.get("title") or "Untitled Product"
        handle = _normalize_handle(p.get("handle") or title)
        vendor = _first_nonempty(p.get("vendor"), vendor_default)
        ptype = _first_nonempty(p.get("type"), type_fallback)

        tags_list, seen = [], set()
        src_tags = p.get("tags")
        if isinstance(src_tags, list): tags_list.extend(src_tags)
        elif src_tags: tags_list.append(str(src_tags))
        for t in extra_tags: tags_list.append(t)
        tags_clean = []
        for t in tags_list:
            if t and t not in seen:
                seen.add(t); tags_clean.append(t)
        tags = ",".join(tags_clean)

        body_html = _first_nonempty(p.get("body_html"), p.get("description_html"), p.get("description"), "")
        images = _filter_images(p.get("images")) or _images_from_html(body_html)
        angles = _angles_from(images, body_html)

        options = p.get("options") or {}
        sizes = options.get(option1_name) or options.get(option1_name.lower()) or options.get("Size") or []
        if (not sizes) and force_single_variant:
            sizes = ["Custom Order"]

        compare_at = p.get("compare_at_price") or ""
        if price_field == "compare_at_or_price_first":
            price = _first_nonempty(p.get("compare_at_price"), p.get("sale_price"), p.get("price"), "")
        else:
            price = _first_nonempty(p.get(price_field), p.get("price"), "")

        variant_rows = []
        if sizes:
            for sz in sizes:
                variant_rows.append({
                    "Option1 Value": sz,
                    "Variant SKU": (p.get("sku_map") or {}).get(sz, p.get("sku") or ""),
                    "Variant Price": price,
                    "Variant Compare At Price": compare_at,
                    "Variant Inventory Qty": p.get("inventory_map", {}).get(sz, p.get("inventory_qty", 50)),
                })
        else:
            variant_rows.append({
                "Option1 Value": "",
                "Variant SKU": p.get("sku") or "",
                "Variant Price": price,
                "Variant Compare At Price": compare_at,
                "Variant Inventory Qty": p.get("inventory_qty", 50),
            })

        def base_row():
            r = {col: "" for col in SHOPIFY_COLUMNS}
            r.update({
                "Handle": handle,
                "Title": title,
                "Body (HTML)": body_html or "",
                "Vendor": vendor,
                "Product Category": product_category,
                "Type": ptype,
                "Tags": tags,
                "Published": published_str,
                "Option1 Name": option1_name if sizes else "",
                "Variant Grams": "",
                "Variant Inventory Tracker": inv_tracker,
                "Variant Inventory Policy": inv_policy,
                "Variant Fulfillment Service": fulfill_service,
                "Variant Requires Shipping": "TRUE",
                "Variant Taxable": "TRUE",
                "Variant Barcode": "",
                "Gift Card": "FALSE",
                "SEO Title": (title[:70] if seo_mode=="auto" else (seo_title_default or "")[:70]),
                "SEO Description": (re.sub(r"<[^>]+>", " ", body_html or "").strip()[:300] if seo_mode=="auto" else (seo_desc_default or "")[:300]),
                "Status": status,
            })
            return r

        first_image = angles[0] if angles else ""
        for idx, v in enumerate(variant_rows):
            r = base_row()
            r.update({
                "Option1 Value": v["Option1 Value"],
                "Variant SKU": v["Variant SKU"],
                "Variant Price": v["Variant Price"],
                "Variant Compare At Price": v["Variant Compare At Price"],
                "Variant Inventory Qty": v["Variant Inventory Qty"],
            })
            if variant_image_strategy == "rotate" and angles:
                r["Variant Image"] = angles[idx % len(angles)]
            if image_strategy == "first_variant" and idx == 0 and first_image:
                r["Image Src"] = first_image
                r["Image Position"] = "1"
                r["Image Alt Text"] = title if image_alt_from_title else r.get("Image Alt Text","")
            if image_strategy == "all_variants" and first_image:
                r["Image Src"] = first_image
                r["Image Position"] = "1"
                r["Image Alt Text"] = title if image_alt_from_title else r.get("Image Alt Text","")
            rows.append(r)

        # image-only rows (remaining)
        start_pos = 1
        start_idx = 0
        if image_strategy in ("first_variant","all_variants") and first_image:
            start_pos = 2; start_idx = 1
        pos = start_pos
        for img in angles[start_idx:]:
            r = {col: "" for col in SHOPIFY_COLUMNS}
            r["Handle"] = handle
            r["Image Src"] = img
            r["Image Position"] = str(pos)
            if image_alt_from_title: r["Image Alt Text"] = title
            rows.append(r)
            pos += 1

    return rows

def _is_variant_row(row: dict) -> bool:
    return bool(str(row.get("Variant SKU","")).strip() or str(row.get("Option1 Value","")).strip() or str(row.get("Title","")).strip())

def normalize_images_and_positions(df: pd.DataFrame, image_strategy: str = "first_variant", image_alt_from_title: bool = True) -> pd.DataFrame:
    if df.empty: return df
    HANDLE, IMG, POS, ALT = "Handle", "Image Src", "Image Position", "Image Alt Text"
    cols = list(df.columns)
    blocks = []
    for handle, g in df.groupby(HANDLE, sort=False):
        g = g.copy()
        raw = [str(u).strip() for u in g.get(IMG, "").tolist() if str(u).strip()]
        if IMG in g.columns: g[IMG] = ""
        if POS in g.columns: g[POS] = ""
        if ALT in g.columns: g[ALT] = ""
        rows = g.to_dict(orient="records")
        first_var_idx = None
        for i, r in enumerate(rows):
            if _is_variant_row(r): first_var_idx = i; break
        if raw:
            if image_strategy in ("first_variant","all_variants") and first_var_idx is not None:
                first_img = raw[0]
                if image_strategy == "first_variant":
                    rows[first_var_idx][IMG] = first_img
                    rows[first_var_idx][POS] = "1"
                    if image_alt_from_title: rows[first_var_idx][ALT] = rows[first_var_idx].get("Title","")
                else:
                    for r in rows:
                        if _is_variant_row(r):
                            r[IMG] = first_img
                            r[POS] = "1"
                            if image_alt_from_title: r[ALT] = r.get("Title","")
                p = 2
                for img in raw[1:]:
                    blank = {c:"" for c in cols}; blank[HANDLE] = handle
                    blank[IMG] = img; blank[POS] = str(p)
                    if image_alt_from_title: blank[ALT] = rows[first_var_idx].get("Title","") if first_var_idx is not None else ""
                    rows.append(blank); p += 1
            else:
                p = 1
                for img in raw:
                    blank = {c:"" for c in cols}; blank[HANDLE] = handle
                    blank[IMG] = img; blank[POS] = str(p)
                    if image_alt_from_title:
                        titles = [str(rr.get("Title","")).strip() for rr in rows if str(rr.get("Title","")).strip()]
                        blank[ALT] = titles[0] if titles else ""
                    rows.append(blank); p += 1
        blocks.extend(rows)
    return pd.DataFrame(blocks, columns=cols)

def write_shopify_csv(df: pd.DataFrame) -> bytes:
    for col in SHOPIFY_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[SHOPIFY_COLUMNS]
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")
