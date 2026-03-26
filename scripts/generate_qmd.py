#!/usr/bin/env python3
"""
generate_qmd.py — IFID Quarto Pipeline Generator
=================================================
Reads data/v030/ifid_encyclopedia_v020.json and outputs:
  - quarto/_quarto.yml          (website config)
  - quarto/_quarto-book.yml     (book/PDF config)
  - quarto/custom.scss          (styling)
  - quarto/index.qmd            (main landing page)
  - quarto/{category}/index.qmd (8 category listing pages)
  - quarto/{category}/{slug}.qmd (623 ingredient pages)

Run from repo root:
  python3 scripts/generate_qmd.py
"""

import json
import os
import re
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────
BASE      = Path(__file__).resolve().parent.parent
JSON_FILE = BASE / "data" / "v030" / "ifid_encyclopedia_v020.json"
OUT_DIR   = BASE / "quarto"

# ─── Category name → slug mapping ─────────────────────────────
CAT_SLUG = {
    "Additives & Functional":    "additives-functional",
    "Dairy & Alternatives":      "dairy-alternatives",
    "Fruits, Veg & Botanicals":  "fruits-veg-botanicals",
    "Oils & Fats":               "oils-fats",
    "Proteins & Meats":          "proteins-meats",
    "Spices & Seasonings":       "spices-seasonings",
    "Staples (Grains/Dals)":     "staples",
    "Sweeteners":                "sweeteners",
}

# Display names (plain, no HTML escaping)
CAT_DISPLAY = {
    "additives-functional":  "Additives & Functional",
    "dairy-alternatives":    "Dairy & Alternatives",
    "fruits-veg-botanicals": "Fruits, Veg & Botanicals",
    "oils-fats":             "Oils & Fats",
    "proteins-meats":        "Proteins & Meats",
    "spices-seasonings":     "Spices & Seasonings",
    "staples":               "Staples (Grains/Dals)",
    "sweeteners":            "Sweeteners",
}

# Navbar short labels
CAT_NAV_LABEL = {
    "additives-functional":  "Additives",
    "dairy-alternatives":    "Dairy",
    "fruits-veg-botanicals": "Botanicals",
    "oils-fats":             "Oils & Fats",
    "proteins-meats":        "Proteins",
    "spices-seasonings":     "Spices",
    "staples":               "Staples",
    "sweeteners":            "Sweeteners",
}

# High-frequency terms to skip interlinking
SKIP_SLUGS = {
    "water", "salt", "sugar", "oil", "milk", "rice", "wheat",
    "butter", "cream", "ghee", "flour", "honey", "vinegar",
    "lemon", "turmeric", "pepper", "chilli", "ginger", "garlic",
    "onion", "curd", "yogurt", "tea", "coffee",
}


# ══════════════════════════════════════════════════════════════
#  LOAD DATA
# ══════════════════════════════════════════════════════════════
def load_data():
    """Returns (metadata, categories) where categories is:
       {cat_slug: {ing_name: {slug, keywords, description{...}}}}
    """
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    metadata = raw["metadata"]
    categories = {}

    for cat_name, items in raw["data"].items():
        cat_slug = CAT_SLUG.get(cat_name)
        if not cat_slug:
            cat_slug = re.sub(r"[^a-z0-9]+", "-", cat_name.lower()).strip("-")

        cat_data = {}
        for ing_name, ing_data in items.items():
            slug = ing_data.get("slug", "")
            json_block = ing_data.get("json", {})
            desc = json_block.get("description", {})
            keywords = json_block.get("keywords", [])
            cat_data[ing_name] = {
                "slug": slug,
                "keywords": keywords,
                "description": desc,
            }
        categories[cat_slug] = cat_data

    return metadata, categories


# ══════════════════════════════════════════════════════════════
#  BUILD SLUG → PATH MAP (for interlinking)
# ══════════════════════════════════════════════════════════════
def build_slug_map(categories):
    """Returns {slug: (cat_slug, ing_name)} for all ingredients."""
    slug_map = {}
    for cat_slug, items in categories.items():
        for ing_name, ing_data in items.items():
            slug = ing_data["slug"]
            if slug:
                slug_map[slug] = (cat_slug, ing_name)
    return slug_map


# ══════════════════════════════════════════════════════════════
#  INTERLINKING
# ══════════════════════════════════════════════════════════════
def interlink_text(text, current_cat_slug, slug_map, categories):
    """
    Replace first-occurrence ingredient name mentions with relative .qmd links.
    Skips SKIP_SLUGS. Longest-name-first to prevent partial matches.
    """
    # Build name → (slug, cat_slug) sorted by name length descending
    candidates = []
    for cat_slug, items in categories.items():
        for ing_name, ing_data in items.items():
            slug = ing_data["slug"]
            if not slug or slug in SKIP_SLUGS:
                continue
            candidates.append((ing_name, slug, cat_slug))
    candidates.sort(key=lambda x: len(x[0]), reverse=True)

    seen = set()
    for ing_name, slug, cat_slug in candidates:
        if ing_name in seen:
            continue
        # Relative path from current category dir to target
        if cat_slug == current_cat_slug:
            rel_path = f"{slug}.qmd"
        else:
            rel_path = f"../{cat_slug}/{slug}.qmd"

        # Match whole-word, case-sensitive, not already inside a link
        pattern = r'(?<!\[)(?<!\()(?<!\w)(' + re.escape(ing_name) + r')(?!\w)(?!\))'
        def make_link(m, rel=rel_path, name=ing_name):
            return f"[{m.group(1)}]({rel})"

        new_text, count = re.subn(pattern, make_link, text, count=1)
        if count > 0:
            seen.add(ing_name)
            text = new_text

    return text


# ══════════════════════════════════════════════════════════════
#  GENERATE INGREDIENT .QMD
# ══════════════════════════════════════════════════════════════
def write_ingredient_qmd(ing_name, ing_data, cat_slug, out_dir, slug_map, categories):
    slug = ing_data["slug"]
    if not slug:
        print(f"  SKIP (no slug): {ing_name}")
        return

    desc = ing_data["description"]
    keywords = ing_data["keywords"]

    history     = desc.get("history_and_sourcing", "")
    culinary    = desc.get("culinary_usage_home", "")
    industrial  = desc.get("industrial_applications", "")
    distinction = desc.get("distinction_and_confusion", "")

    # Short description from first sentence of history (~160 chars)
    short_desc = history.split(".")[0].strip()
    if len(short_desc) > 160:
        short_desc = short_desc[:157] + "..."

    # Interlink each section
    history     = interlink_text(history,     cat_slug, slug_map, categories)
    culinary    = interlink_text(culinary,    cat_slug, slug_map, categories)
    industrial  = interlink_text(industrial,  cat_slug, slug_map, categories)
    distinction = interlink_text(distinction, cat_slug, slug_map, categories)

    # Build keywords YAML list
    kw_yaml = ", ".join(f'"{k}"' for k in keywords)

    content = f"""---
title: "{ing_name.replace('"', '\\"')}"
slug: {slug}
category: "{CAT_DISPLAY[cat_slug].replace('"', '\\"')}"
category-slug: {cat_slug}
keywords: [{kw_yaml}]
description: "{short_desc.replace('"', '\\"')}"
---

## History and Sourcing

{history}

## Home Kitchen Use

{culinary}

## Industrial Applications

{industrial}

## Distinctions and Common Confusion

{distinction}
"""

    out_path = out_dir / cat_slug / f"{slug}.qmd"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")


# ══════════════════════════════════════════════════════════════
#  GENERATE CATEGORY INDEX .QMD
# ══════════════════════════════════════════════════════════════
def write_category_index(cat_slug, items, out_dir):
    display = CAT_DISPLAY[cat_slug]
    count = len(items)
    # Collect all slugs for listing (sorted by ingredient name)
    sorted_items = sorted(items.keys())

    content = f"""---
title: "{display}"
listing:
  contents: "*.qmd"
  sort: "title asc"
  type: table
  fields: [title, description]
  exclude:
    slug: "{cat_slug}"
---

*{count} ingredients in this category.*
"""

    out_path = out_dir / cat_slug / "index.qmd"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")


# ══════════════════════════════════════════════════════════════
#  GENERATE MAIN INDEX .QMD
# ══════════════════════════════════════════════════════════════
def write_main_index(categories, metadata, out_dir):
    total = sum(len(v) for v in categories.values())

    # Build category cards section
    cards = []
    for cat_slug in CAT_SLUG.values():
        display = CAT_DISPLAY[cat_slug]
        count = len(categories.get(cat_slug, {}))
        cards.append(f"- **[{display}]({cat_slug}/index.qmd)** — {count} ingredients")

    cards_md = "\n".join(cards)

    content = f"""---
title: "Encyclopedia of Indian Food Ingredients"
subtitle: "IFID v2.0 · {total} ingredients · 8 categories"
---

## About This Encyclopedia

The **Indian Food Ingredients Database (IFID)** is a standardized taxonomy of food components found in the Indian food ecosystem — from traditional botanicals and Ayurvedic herbs to modern food additives and functional ingredients.

This encyclopedia bridges traditional knowledge and contemporary FMCG standards, providing structured, sourced descriptions of each ingredient across four dimensions:

- **History & Sourcing** — origin, cultivation, and historical use in India
- **Home Kitchen Use** — how the ingredient appears in domestic cooking
- **Industrial Applications** — role in packaged food manufacturing
- **Distinctions & Common Confusion** — how to tell it apart from similar ingredients

**Version:** {metadata.get('version', '0.2.0-alpha')}
**DOI:** [{metadata.get('doi', '')}]({metadata.get('doi', '')})
**License:** {metadata.get('license', 'ODC-By')}
**Author:** {metadata.get('author', 'Lalitha A R')}, {metadata.get('institution', 'iSRL')}

---

## Categories

{cards_md}

---

*Cite as: {metadata.get('author', 'Lalitha A R')} ({metadata.get('release_date', '2026')[:4]}). {metadata.get('title', 'Encyclopedia of Indian Food Ingredients')}. {metadata.get('institution', 'iSRL')}. DOI: {metadata.get('doi', '')}*
"""

    out_path = out_dir / "index.qmd"
    out_path.write_text(content, encoding="utf-8")


# ══════════════════════════════════════════════════════════════
#  GENERATE _QUARTO.YML (website)
# ══════════════════════════════════════════════════════════════
def write_quarto_yml(out_dir):
    # Build navbar items for all 8 categories in order
    nav_items = []
    for cat_slug in CAT_SLUG.values():
        label = CAT_NAV_LABEL[cat_slug]
        nav_items.append(f'      - text: "{label}"\n        href: {cat_slug}/index.qmd')
    nav_yaml = "\n".join(nav_items)

    content = f"""project:
  type: website
  output-dir: _site

website:
  title: "Encyclopedia of Indian Food Ingredients"
  description: "A standardized taxonomy of 623 food components in the Indian ecosystem."
  repo-url: https://github.com/isrl-research/ifid-encyclopedia
  navbar:
    left:
      - text: "Home"
        href: index.qmd
{nav_yaml}
  search: true
  page-footer:
    left: "© 2026 Lalitha A R, iSRL · ODC-By License"
    right: "DOI: 10.5281/zenodo.18650862"

format:
  html:
    theme: [flatly, custom.scss]
    toc: true
    toc-depth: 2
    smooth-scroll: true
"""

    out_path = out_dir / "_quarto.yml"
    out_path.write_text(content, encoding="utf-8")


# ══════════════════════════════════════════════════════════════
#  GENERATE _QUARTO-BOOK.YML (PDF book)
# ══════════════════════════════════════════════════════════════
def write_quarto_book_yml(categories, out_dir):
    parts = []
    for cat_slug in CAT_SLUG.values():
        display = CAT_DISPLAY[cat_slug]
        items = categories.get(cat_slug, {})
        # Sort chapters alphabetically by ingredient name
        slugs = sorted(
            (ing["slug"] for ing in items.values() if ing["slug"]),
            key=lambda s: s
        )
        chapter_lines = "\n".join(f'        - {cat_slug}/{s}.qmd' for s in slugs)
        parts.append(f"""    - part: "{display}"
      chapters:
        - {cat_slug}/index.qmd
{chapter_lines}""")

    parts_yaml = "\n".join(parts)

    content = f"""project:
  type: book
  output-dir: _book

book:
  title: "Encyclopedia of Indian Food Ingredients"
  subtitle: "IFID v2.0"
  author: "Lalitha A R"
  date: "2026"
  doi: "10.5281/zenodo.18650862"
  chapters:
    - index.qmd
{parts_yaml}

format:
  pdf:
    documentclass: scrbook
    classoption: [oneside]
    papersize: a4
    fontsize: 10pt
    toc: true
    toc-depth: 1
    lof: false
    lot: false
"""

    out_path = out_dir / "_quarto-book.yml"
    out_path.write_text(content, encoding="utf-8")


# ══════════════════════════════════════════════════════════════
#  GENERATE CUSTOM.SCSS
# ══════════════════════════════════════════════════════════════
def write_custom_scss(out_dir):
    content = """/*
  IFID Encyclopedia — custom.scss
  Adapts iSRL ency.css palette & typography for Quarto's flatly theme.
*/

/*-- scss:defaults --*/

/* ─── Variables ─────────────────────────────────────────────── */
$bg:          #f7f6f2;
$ink:         #111110;
$ink-mid:     #3a3a38;
$ink-muted:   #5a5a57;
$navy:        #2c346b;
$red:         #c0392b;
$rule:        #d0cfc8;
$rule-light:  #e4e3dd;

$font-title:  'Libre Baskerville', Georgia, serif;
$font-body:   'Source Serif 4', Georgia, serif;
$font-mono:   'DM Mono', 'Courier New', monospace;

/*-- scss:rules --*/

/* ─── Google Fonts ─────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=DM+Mono:wght@400;500&display=swap');

/* ─── Body & Typography ─────────────────────────────────────── */
body {
  background-color: $bg;
  color: $ink;
  font-family: $font-body;
  font-size: 1.05rem;
  line-height: 1.75;
}

h1, h2, h3, h4, h5, h6 {
  font-family: $font-title;
  color: $ink;
  font-weight: 700;
}

h1 {
  font-size: 2rem;
  border-bottom: 2px solid $ink;
  padding-bottom: 0.4rem;
  margin-bottom: 1.25rem;
}

h2 {
  font-size: 1.35rem;
  color: $navy;
  margin-top: 2rem;
  margin-bottom: 0.75rem;
}

/* ─── Links ─────────────────────────────────────────────────── */
a {
  color: $navy;
  text-decoration: underline;
  text-underline-offset: 2px;
}

a:hover {
  color: $red;
}

/* ─── Navbar ────────────────────────────────────────────────── */
.navbar {
  background-color: $navy !important;
  border-bottom: 2px solid darken($navy, 8%);
}

.navbar .navbar-brand,
.navbar .nav-link {
  color: #fff !important;
  font-family: $font-mono;
  font-size: 0.85rem;
  letter-spacing: 0.04em;
}

.navbar .nav-link:hover {
  color: rgba(255,255,255,0.75) !important;
}

/* ─── TOC ───────────────────────────────────────────────────── */
#TOC {
  font-family: $font-mono;
  font-size: 0.8rem;
}

#TOC a {
  color: $ink-muted;
  text-decoration: none;
}

#TOC a:hover {
  color: $navy;
}

/* ─── Page content ──────────────────────────────────────────── */
.quarto-title-meta {
  font-family: $font-mono;
  font-size: 0.78rem;
  color: $ink-muted;
}

/* INS codes and monospace spans */
code {
  font-family: $font-mono;
  font-size: 0.85em;
  background: rgba(44, 52, 107, 0.07);
  padding: 0.1em 0.35em;
  border-radius: 3px;
  color: $navy;
}

/* ─── Keywords / category tags (from listing pages) ────────── */
.quarto-listing-category {
  font-family: $font-mono;
  font-size: 0.7rem;
  background: rgba(44, 52, 107, 0.08);
  color: $navy;
  border: 1px solid rgba(44, 52, 107, 0.2);
  border-radius: 3px;
  padding: 0.1rem 0.45rem;
  display: inline-block;
  margin: 0.1rem 0.15rem;
}

/* ─── Listing table ─────────────────────────────────────────── */
.quarto-listing-table td {
  font-size: 0.95rem;
}

.quarto-listing-table thead {
  font-family: $font-mono;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: $ink-muted;
}

/* ─── Footer ────────────────────────────────────────────────── */
.nav-footer {
  background: $ink;
  color: #ccc;
  font-family: $font-mono;
  font-size: 0.75rem;
  padding: 1rem 2rem;
}

.nav-footer a {
  color: #aaa;
}

/* ─── Blockquotes ───────────────────────────────────────────── */
blockquote {
  border-left: 3px solid $navy;
  padding-left: 1rem;
  color: $ink-mid;
  font-style: italic;
}

/* ─── Responsive ────────────────────────────────────────────── */
@media (max-width: 768px) {
  body {
    font-size: 1rem;
  }

  h1 {
    font-size: 1.6rem;
  }

  h2 {
    font-size: 1.2rem;
  }
}
"""

    out_path = out_dir / "custom.scss"
    out_path.write_text(content, encoding="utf-8")


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════
def main():
    print("Loading JSON data...")
    metadata, categories = load_data()

    total = sum(len(v) for v in categories.values())
    print(f"Loaded {total} ingredients across {len(categories)} categories")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Building slug map...")
    slug_map = build_slug_map(categories)

    print("Generating _quarto.yml...")
    write_quarto_yml(OUT_DIR)

    print("Generating _quarto-book.yml...")
    write_quarto_book_yml(categories, OUT_DIR)

    print("Generating custom.scss...")
    write_custom_scss(OUT_DIR)

    print("Generating main index.qmd...")
    write_main_index(categories, metadata, OUT_DIR)

    print("Generating category index pages...")
    for cat_slug, items in categories.items():
        write_category_index(cat_slug, items, OUT_DIR)

    print("Generating ingredient pages...")
    count = 0
    for cat_slug, items in categories.items():
        for ing_name, ing_data in items.items():
            write_ingredient_qmd(
                ing_name, ing_data, cat_slug, OUT_DIR, slug_map, categories
            )
            count += 1
            if count % 50 == 0:
                print(f"  {count}/{total}...")

    print(f"\nDone! Generated {count} ingredient pages + 8 category indexes + main index")
    print(f"Output: {OUT_DIR}/")


if __name__ == "__main__":
    main()
