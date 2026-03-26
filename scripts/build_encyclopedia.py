#!/usr/bin/env python3
"""
build_encyclopedia.py — IFID Encyclopedia Site Builder
======================================================
Reads v030 MD ingredient files + JSON data, then:
  1. Normalises MD headings to uniform '# Name' format
  2. Interlinks ingredient mentions (skipping high-frequency terms)
  3. Generates category index pages + main index (ency.md)
  4. Converts all MD → HTML body via pandoc, wraps in template
  5. Copies CSS to output
  6. Generates sitemap.xml

Output: data/v030/site/
"""

import json
import os
import re
import subprocess
import shutil
from pathlib import Path
from html import escape as html_escape

# ─── Paths ────────────────────────────────────────────────────
BASE        = Path(__file__).resolve().parent.parent
V030        = BASE / "data" / "v030"
MD_DIR      = V030 / "md"
JSON_FILE   = V030 / "ifid_encyclopedia_v020.json"
SITE_DIR    = V030 / "site"
ENCY_SUBDIR = SITE_DIR / "ency"
CSS_SRC     = BASE / "scripts" / "ency.css"

SITE_URL_BASE = "https://isrl-research.github.io/ifid"
# Main index is at ifid/ency.html
MAIN_INDEX_URL = SITE_URL_BASE + "/ency.html"
# Categories and ingredients are under ifid/ency/
ENCY_URL_BASE = SITE_URL_BASE + "/ency"
IFID_HOME_URL = "https://isrl-research.github.io/ifid.html"

# ─── High-frequency terms to SKIP interlinking ───────────────
SKIP_SLUGS = {
    "water", "salt", "sugar", "oil", "milk", "rice", "wheat",
    "butter", "cream", "ghee", "flour", "honey", "vinegar",
    "lemon", "turmeric", "pepper", "chilli", "ginger", "garlic",
    "onion", "curd", "yogurt", "tea", "coffee",
}

# Category slug → display name
CAT_DISPLAY = {
    "additives-functional":  "Additives &amp; Functional",
    "dairy-alternatives":    "Dairy &amp; Alternatives",
    "fruits-veg-botanicals": "Fruits, Veg &amp; Botanicals",
    "oils-fats":             "Oils &amp; Fats",
    "proteins-meats":        "Proteins &amp; Meats",
    "spices-seasonings":     "Spices &amp; Seasonings",
    "staples":               "Staples (Grains/Dals)",
    "sweeteners":            "Sweeteners",
}

# Non-escaped version for JSON matching
CAT_DISPLAY_PLAIN = {
    "additives-functional":  "Additives & Functional",
    "dairy-alternatives":    "Dairy & Alternatives",
    "fruits-veg-botanicals": "Fruits, Veg & Botanicals",
    "oils-fats":             "Oils & Fats",
    "proteins-meats":        "Proteins & Meats",
    "spices-seasonings":     "Spices & Seasonings",
    "staples":               "Staples (Grains/Dals)",
    "sweeteners":            "Sweeteners",
}


# ══════════════════════════════════════════════════════════════
#  STEP 1: Load ingredient map from JSON
# ══════════════════════════════════════════════════════════════
def load_ingredient_map():
    """Returns dict: {ingredient_name: {slug, cat_slug, keywords}}"""
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    ingredients = {}
    for cat_name, items in data["data"].items():
        cat_slug = None
        for slug, display in CAT_DISPLAY_PLAIN.items():
            if display == cat_name:
                cat_slug = slug
                break
        if not cat_slug:
            cat_slug = re.sub(r"[^a-z0-9]+", "-", cat_name.lower()).strip("-")

        for ing_name, ing_data in items.items():
            slug = ing_data.get("slug", "")
            kw = ing_data.get("json", {}).get("keywords", [])
            ingredients[ing_name] = {
                "slug": slug,
                "cat_slug": cat_slug,
                "cat_display": CAT_DISPLAY.get(cat_slug, cat_slug),
                "keywords": kw,
            }
    return ingredients


# ══════════════════════════════════════════════════════════════
#  STEP 2: Normalise MD files
# ══════════════════════════════════════════════════════════════
def normalise_md_files(ingredient_map):
    slug_to_name = {}
    for name, info in ingredient_map.items():
        slug_to_name[info["slug"]] = name

    count = 0
    for md_path in sorted(MD_DIR.rglob("*.md")):
        if md_path.name.startswith("_"):
            continue
        slug = md_path.stem
        expected_name = slug_to_name.get(slug, slug.replace("-", " ").title())

        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        first_line = lines[0].strip() if lines else ""

        if first_line.startswith("# ") and not first_line.startswith("## "):
            continue

        new_lines = []
        if first_line.startswith("### ") or first_line.startswith("## "):
            heading_text = re.sub(r"^#{2,}\s*", "", first_line)
            new_lines.append(f"# {heading_text}")
            new_lines.extend(lines[1:])
        elif first_line.startswith("**") and first_line.endswith("**"):
            heading_text = first_line.strip("* ")
            new_lines.append(f"# {heading_text}")
            rest = lines[1:]
            if rest and rest[0].strip() == "":
                rest = rest[1:]
            new_lines.extend(rest)
        elif first_line.startswith("**"):
            heading_match = re.match(r"\*\*([^*]+)\*\*", first_line)
            if heading_match:
                new_lines.append(f"# {heading_match.group(1).strip()}")
                remainder = first_line[heading_match.end():].strip()
                if remainder:
                    new_lines.append("")
                    new_lines.append(remainder)
                new_lines.extend(lines[1:])
            else:
                new_lines.append(f"# {expected_name}")
                new_lines.append("")
                new_lines.extend(lines)
        else:
            new_lines.append(f"# {expected_name}")
            new_lines.append("")
            new_lines.extend(lines)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines))
        count += 1

    print(f"  Normalised {count} MD files")


# ══════════════════════════════════════════════════════════════
#  STEP 3: Interlink MD files
# ══════════════════════════════════════════════════════════════
def interlink_md_files(ingredient_map):
    link_targets = []
    for name, info in ingredient_map.items():
        if info["slug"] in SKIP_SLUGS:
            continue
        url = f"{ENCY_URL_BASE}/{info['cat_slug']}/{info['slug']}.html"
        link_targets.append((name, url, info["slug"]))

    link_targets.sort(key=lambda x: len(x[0]), reverse=True)

    total_links = 0
    for md_path in sorted(MD_DIR.rglob("*.md")):
        if md_path.name.startswith("_"):
            continue
        current_slug = md_path.stem
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n", 1)
        if len(lines) < 2:
            continue
        heading = lines[0]
        body = lines[1]

        linked_slugs = set()
        file_links = 0

        for name, url, slug in link_targets:
            if slug == current_slug:
                continue
            if slug in linked_slugs:
                continue

            pattern = re.compile(
                r'(?<!\[)(?<!\w)(' + re.escape(name) + r')(?!\w)(?!\])(?!\()',
                re.IGNORECASE
            )

            match = pattern.search(body)
            if match:
                matched_text = match.group(1)
                replacement = f"[{matched_text}]({url})"
                body = body[:match.start()] + replacement + body[match.end():]
                linked_slugs.add(slug)
                file_links += 1

        if file_links > 0:
            content = heading + "\n" + body
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(content)
            total_links += file_links

    print(f"  Added {total_links} cross-links across all files")


# ══════════════════════════════════════════════════════════════
#  STEP 4: Generate index pages (MD)
# ══════════════════════════════════════════════════════════════
def generate_index_pages(ingredient_map):
    categories = {}
    for name, info in ingredient_map.items():
        cat = info["cat_slug"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((name, info["slug"]))

    for cat in categories:
        categories[cat].sort(key=lambda x: x[0].lower())

    for cat_slug, items in categories.items():
        cat_display = CAT_DISPLAY_PLAIN.get(cat_slug, cat_slug)
        cat_dir = MD_DIR / cat_slug
        cat_dir.mkdir(exist_ok=True)

        lines = [
            f"# {cat_display}",
            "",
            f"*{len(items)} ingredients in this category.*",
            "",
        ]

        for name, slug in items:
            url = f"{ENCY_URL_BASE}/{cat_slug}/{slug}.html"
            lines.append(f"- [{name}]({url})")

        lines.append("")
        index_path = cat_dir / "_index.md"
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # Main index
    lines = [
        "# Encyclopedia of Indian Food Ingredients",
        "",
        "A comprehensive taxonomy of 623 food components in the Indian ecosystem,",
        "bridging traditional knowledge and FMCG standards.",
        "",
        "---",
        "",
    ]

    total = 0
    for cat_slug in sorted(categories.keys()):
        cat_display = CAT_DISPLAY_PLAIN.get(cat_slug, cat_slug)
        count = len(categories[cat_slug])
        total += count
        url = f"{ENCY_URL_BASE}/{cat_slug}/index.html"
        lines.append(f"### [{cat_display}]({url})")
        lines.append(f"*{count} ingredients*")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"**Total: {total} ingredients across {len(categories)} categories**")
    lines.append("")

    ency_path = MD_DIR / "_ency.md"
    with open(ency_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  Created {len(categories)} category index pages + main index")


# ══════════════════════════════════════════════════════════════
#  STEP 5: Build HTML
# ══════════════════════════════════════════════════════════════
def md_to_html_body(md_path):
    """Use pandoc to convert MD → HTML5 fragment (body only)."""
    result = subprocess.run(
        ["pandoc", str(md_path), "--from", "markdown", "--to", "html5", "--no-highlight"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ERROR pandoc: {md_path.name}: {result.stderr[:200]}")
        return ""
    return result.stdout


def build_nav_items(cat_slug_active):
    """Build the category nav list HTML."""
    items = []
    items.append(f'          <li><a href="{IFID_HOME_URL}">← IFID Home</a></li>')
    items.append(f'          <li><a href="{MAIN_INDEX_URL}">All Categories</a></li>')
    for slug, display in sorted(CAT_DISPLAY.items()):
        active = ' class="active"' if slug == cat_slug_active else ""
        items.append(f'          <li><a href="{ENCY_URL_BASE}/{slug}/index.html"{active}>{display}</a></li>')
    return "\n".join(items)


def build_keywords_html(keywords):
    """Build keyword tags HTML for right sidebar."""
    if not keywords:
        return ""
    tags = "\n".join(f'          <span class="ency-keyword" role="listitem">{html_escape(k)}</span>' for k in keywords)
    return f"""
    <div class="ency-right-section">
      <span class="ency-right-label">Keywords</span>
      <div class="ency-right-meta">
        <div class="ency-keywords" role="list">
{tags}
        </div>
      </div>
    </div>"""


def build_page(body_html, title, description, keywords_str, cat_slug, cat_display,
               css_path, canonical_url, ingredient_name=None, keywords_list=None):
    """Build a complete HTML page wrapping the body content."""
    safe_title = html_escape(title)
    safe_desc = html_escape(description)
    nav_items = build_nav_items(cat_slug)
    kw_html = build_keywords_html(keywords_list or [])

    breadcrumb_trail = f'''        <a href="{MAIN_INDEX_URL}">Encyclopedia</a>
        <span class="sep" aria-hidden="true">›</span>
        <a href="{ENCY_URL_BASE}/{cat_slug}/index.html">{cat_display}</a>'''
    if ingredient_name:
        breadcrumb_trail += f'''
        <span class="sep" aria-hidden="true">›</span>
        <span aria-current="page">{html_escape(ingredient_name)}</span>'''

    nav_footer = f'''      <nav class="ency-nav-footer" aria-label="Page navigation">
        <a href="{MAIN_INDEX_URL}">← Encyclopedia Index</a>
        <span class="sep" aria-hidden="true">·</span>
        <a href="{ENCY_URL_BASE}/{cat_slug}/index.html">{cat_display}</a>
        <span class="sep" aria-hidden="true">·</span>
        <a href="{IFID_HOME_URL}">IFID Home</a>
      </nav>'''

    # Mobile nav items (same categories)
    mobile_nav = []
    mobile_nav.append(f'    <li><a href="{IFID_HOME_URL}">IFID Home</a></li>')
    mobile_nav.append(f'    <li><a href="{MAIN_INDEX_URL}">Encyclopedia</a></li>')
    for slug, display in sorted(CAT_DISPLAY.items()):
        mobile_nav.append(f'    <li><a href="{ENCY_URL_BASE}/{slug}/index.html">{display}</a></li>')
    mobile_nav_html = "\n".join(mobile_nav)

    # JSON-LD
    ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "name": title,
        "headline": title,
        "description": description,
        "author": {
            "@type": "Person",
            "name": "Lalitha A R",
            "affiliation": {
                "@type": "Organization",
                "name": "Interdisciplinary Systems Research Lab (iSRL)",
                "url": "https://isrl-research.github.io"
            }
        },
        "datePublished": "2026-02-25",
        "publisher": {
            "@type": "Organization",
            "name": "Interdisciplinary Systems Research Lab (iSRL)",
            "url": "https://isrl-research.github.io"
        },
        "license": "https://opendatacommons.org/licenses/by/1-0/",
        "isPartOf": {
            "@type": "Collection",
            "name": "IFID Encyclopedia of Indian Food Ingredients",
            "url": MAIN_INDEX_URL
        },
        "isAccessibleForFree": True,
        "inLanguage": "en"
    }
    ld_json = json.dumps(ld, indent=2, ensure_ascii=False)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-8PD6FFEJEV"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag("js", new Date());

  gtag("config", "G-8PD6FFEJEV");
</script>

<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{safe_title} — iSRL</title>

<!-- SEO -->
<meta name="description" content="{safe_desc}">
<meta name="author" content="Lalitha A R">
<meta name="keywords" content="{html_escape(keywords_str)}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{canonical_url}">

<!-- DOI and Citation -->
<meta name="citation_doi" content="10.5281/zenodo.18650862">
<meta name="citation_publication_date" content="2026-02-25">
<meta name="citation_author" content="Lalitha, A. R.">
<meta name="citation_title" content="Encyclopedia of Indian Food Ingredients: A Standardized Taxonomy for Indian Food Informatics">
<meta name="citation_publisher" content="Interdisciplinary Systems Research Lab">
<meta name="citation_full_citation" content="Lalitha, A. R. (2026). Encyclopedia of Indian Food Ingredients: A Standardized Taxonomy for Indian Food Informatics. Interdisciplinary Systems Research Lab.">

<!-- Open Graph -->
<meta property="og:type" content="article">
<meta property="og:title" content="{safe_title} — iSRL">
<meta property="og:description" content="{safe_desc}">
<meta property="og:site_name" content="iSRL — Interdisciplinary Systems Research Lab">
<meta property="og:url" content="{canonical_url}">

<!-- Twitter -->
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{safe_title} — iSRL">
<meta name="twitter:description" content="{safe_desc}">

<!-- Dublin Core -->
<meta name="DC.title" content="{safe_title}">
<meta name="DC.creator" content="Lalitha A R">
<meta name="DC.date" content="2026-02-25">
<meta name="DC.type" content="Encyclopedia Entry">
<meta name="DC.publisher" content="Interdisciplinary Systems Research Lab (iSRL)">
<meta name="DC.rights" content="ODC-By">
<meta name="DC.identifier" content="doi:10.5281/zenodo.18650862">
<meta name="DC.source" content="https://www.doi.org/10.5281/zenodo.18650862">

<script type="application/ld+json">
{ld_json}
</script>

<link rel="stylesheet" href="{css_path}" type="text/css">
</head>
<body>

<a href="#ency-main" class="ency-skip-link">Skip to main content</a>

<!-- Mobile header -->
<header class="ency-mobile-header" role="banner">
  <a href="{MAIN_INDEX_URL}" class="ency-mobile-logo" aria-label="IFID Encyclopedia">
    <span class="logo-i">i</span>SRL
  </a>
  <button class="ency-hamburger" id="ency-hamburger" aria-label="Open navigation" aria-expanded="false" aria-controls="ency-mobile-drawer">
    <span></span><span></span><span></span>
  </button>
</header>

<!-- Mobile nav drawer -->
<nav class="ency-mobile-drawer" id="ency-mobile-drawer" aria-label="Mobile navigation" aria-hidden="true">
  <a href="{MAIN_INDEX_URL}" class="ency-mobile-drawer-logo" aria-label="IFID Encyclopedia">
    <span class="logo-i">i</span>SRL
  </a>
  <ul class="ency-nav-list" role="list">
{mobile_nav_html}
  </ul>
</nav>

<!-- Three-column shell -->
<div class="ency-shell">

  <!-- Left sidebar -->
  <aside class="ency-sidebar" aria-label="Encyclopedia navigation">
    <div class="ency-logo-block">
      <span class="ency-logo-rule" aria-hidden="true"></span>
      <a href="https://isrl-research.github.io/" class="ency-logo-wordmark" aria-label="iSRL home">
        <span class="logo-i">i</span>SRL
      </a>
      <span class="ency-logo-sub">IFID Encyclopedia</span>
    </div>

    <nav aria-label="Categories">
      <button class="ency-nav-toggle" aria-expanded="true" aria-controls="ency-nav-panel" id="ency-nav-toggle">
        <span class="ency-nav-arrow" aria-hidden="true">▶</span>
        Categories
      </button>
      <div class="ency-nav-panel open" id="ency-nav-panel">
        <ul class="ency-nav-list" role="list">
{nav_items}
        </ul>
      </div>
    </nav>

    <div class="ency-toc-divider" aria-hidden="true"></div>

    <div class="ency-sidebar-footer">
      <p>ODC-By · iSRL<br>Data is a permanent public asset</p>
    </div>
  </aside>

  <!-- Main content -->
  <main id="ency-main" class="ency-main" aria-label="Article">
    <div class="ency-content">
      <span class="ency-doc-badge">Encyclopedia</span>
      <nav class="ency-breadcrumb" aria-label="Breadcrumb">
{breadcrumb_trail}
      </nav>

{body_html}

{nav_footer}
    </div>
  </main>

  <!-- Right sidebar -->
  <aside class="ency-right" aria-label="Metadata">
    <div class="ency-right-section">
      <span class="ency-right-label">Category</span>
      <div class="ency-right-meta">
        <a href="{ENCY_URL_BASE}/{cat_slug}/index.html">{cat_display}</a>
      </div>
    </div>
{kw_html}
    <div class="ency-right-section">
      <span class="ency-right-label">Project</span>
      <div class="ency-right-meta">
        <a href="{IFID_HOME_URL}">Indian Food Informatics Data</a><br>
        IFID 2026
      </div>
    </div>
    <div class="ency-right-section">
      <span class="ency-right-label">License</span>
      <div class="ency-right-meta">
        <a href="https://opendatacommons.org/licenses/by/1-0/" target="_blank" rel="noopener noreferrer">ODC-By 1.0</a><br>
        Open Data Commons Attribution
      </div>
    </div>
    <div class="ency-right-footer">
      <p>ODC-By · iSRL<br>Data is a permanent public asset</p>
    </div>
  </aside>

</div>

<script>
(function(){{
  var btn=document.getElementById('ency-nav-toggle');
  var panel=document.getElementById('ency-nav-panel');
  if(!btn||!panel)return;
  btn.addEventListener('click',function(){{
    var open=panel.classList.toggle('open');
    btn.setAttribute('aria-expanded',String(open));
  }});
}})();
(function(){{
  var hambtn=document.getElementById('ency-hamburger');
  var drawer=document.getElementById('ency-mobile-drawer');
  if(!hambtn||!drawer)return;
  function close(){{
    hambtn.setAttribute('aria-expanded','false');
    hambtn.setAttribute('aria-label','Open navigation');
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden','true');
  }}
  hambtn.addEventListener('click',function(){{
    var expanded=hambtn.getAttribute('aria-expanded')==='true';
    if(expanded){{close();}}else{{
      hambtn.setAttribute('aria-expanded','true');
      hambtn.setAttribute('aria-label','Close navigation');
      drawer.classList.add('open');
      drawer.setAttribute('aria-hidden','false');
      var first=drawer.querySelector('a');
      if(first)first.focus();
    }}
  }});
  document.addEventListener('keydown',function(e){{
    if(e.key==='Escape'&&drawer.classList.contains('open')){{close();hambtn.focus();}}
  }});
  drawer.querySelectorAll('a').forEach(function(l){{l.addEventListener('click',close);}});
}})();
</script>

</body>
</html>'''


def build_html(ingredient_map):
    """Convert all MD files to HTML."""
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    ENCY_SUBDIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CSS_SRC, ENCY_SUBDIR / "ency.css")

    slug_info = {}
    for name, info in ingredient_map.items():
        slug_info[info["slug"]] = {
            "name": name,
            "cat_slug": info["cat_slug"],
            "cat_display": info["cat_display"],
            "keywords": info["keywords"],
        }

    urls = []
    total = 0

    # 1. Main index - ency.html at root of site/
    ency_md = MD_DIR / "_ency.md"
    body = md_to_html_body(ency_md)
    page = build_page(
        body, "Encyclopedia of Indian Food Ingredients",
        "A comprehensive taxonomy of 623 food components in the Indian ecosystem.",
        "Indian food, encyclopedia, ingredients, IFID, food informatics",
        "", "Index", "ency/ency.css", MAIN_INDEX_URL, keywords_list=[]
    )
    (SITE_DIR / "ency.html").write_text(page, encoding="utf-8")
    urls.append(MAIN_INDEX_URL)
    total += 1

    # 2. Category index pages - in ency/
    for cat_slug, cat_display in sorted(CAT_DISPLAY.items()):
        cat_dir = ENCY_SUBDIR / cat_slug
        cat_dir.mkdir(exist_ok=True)

        index_md = MD_DIR / cat_slug / "_index.md"
        body = md_to_html_body(index_md)
        canonical = f"{ENCY_URL_BASE}/{cat_slug}/index.html"
        page = build_page(
            body, f"{CAT_DISPLAY_PLAIN[cat_slug]} — IFID Encyclopedia",
            f"Browse all ingredients in the {CAT_DISPLAY_PLAIN[cat_slug]} category.",
            f"{CAT_DISPLAY_PLAIN[cat_slug]}, Indian food, IFID",
            cat_slug, cat_display, "../ency.css", canonical, keywords_list=[]
        )
        (cat_dir / "index.html").write_text(page, encoding="utf-8")
        urls.append(canonical)
        total += 1

    # 3. Individual ingredient pages - in ency/
    for md_path in sorted(MD_DIR.rglob("*.md")):
        if md_path.name.startswith("_"):
            continue

        slug = md_path.stem
        cat_slug = md_path.parent.name
        cat_dir = ENCY_SUBDIR / cat_slug
        cat_dir.mkdir(exist_ok=True)

        info = slug_info.get(slug, {})
        name = info.get("name", slug.replace("-", " ").title())
        cat_display = info.get("cat_display", CAT_DISPLAY.get(cat_slug, cat_slug))
        keywords = info.get("keywords", [])

        body = md_to_html_body(md_path)
        desc = f"Learn about {name}: history, culinary usage, industrial applications in the IFID Encyclopedia."
        kw_str = ", ".join(keywords) if keywords else f"{name}, Indian food, IFID"
        canonical = f"{ENCY_URL_BASE}/{cat_slug}/{slug}.html"

        page = build_page(
            body, f"{name} — IFID Encyclopedia",
            desc, kw_str,
            cat_slug, cat_display, "../ency.css", canonical,
            ingredient_name=name, keywords_list=keywords
        )
        (cat_dir / f"{slug}.html").write_text(page, encoding="utf-8")
        urls.append(canonical)
        total += 1

    print(f"  Generated {total} HTML files")
    generate_sitemap(urls)


def generate_sitemap(urls):
    """Generate sitemap.xml in the ency subfolder."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        lines.append('  <url>')
        lines.append(f'    <loc>{url}</loc>')
        lines.append('    <changefreq>monthly</changefreq>')
        lines.append('    <priority>0.5</priority>')
        lines.append('  </url>')
    lines.append('</urlset>')
    
    sitemap_path = ENCY_SUBDIR / "sitemap.xml"
    sitemap_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Generated sitemap.xml with {len(urls)} URLs at {sitemap_path}")


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("IFID Encyclopedia Builder")
    print("=" * 60)

    print("\n1. Loading ingredient map...")
    ingredient_map = load_ingredient_map()
    print(f"   {len(ingredient_map)} ingredients loaded")

    print("\n2. Normalising MD files...")
    normalise_md_files(ingredient_map)

    print("\n3. Interlinking MD files...")
    interlink_md_files(ingredient_map)

    print("\n4. Generating index pages...")
    generate_index_pages(ingredient_map)

    print("\n5. Building HTML...")
    build_html(ingredient_map)

    print("\n" + "=" * 60)
    print(f"Done! Site at: {SITE_DIR}")
    print("=" * 60)
