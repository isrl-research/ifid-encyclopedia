#!/usr/bin/env python3
"""
isrl-publish.py — iSRL Research Log Publisher
==============================================
Takes a raw LaTeXML-converted HTML file and transforms it into a
fully-styled, SEO-complete iSRL research log page.

Usage:
    python3 isrl-publish.py path/to/paper.html

What it does:
  1. Reads the raw LaTeXML HTML (minimal head, bare body)
  2. Extracts title, authors, date, abstract from ltx_* classes
  3. Extracts section headings for ToC
  4. Prompts for: Zenodo DOI, publication date, document type, canonical URL
  5. Replaces the head with a complete SEO-ready head:
       - charset, viewport, title
       - meta description, OG tags, Twitter card
       - Dublin Core, citation_* tags for Google Scholar
       - JSON-LD (ScholarlyArticle / TechArticle)
       - link to res-log.css
  6. Wraps the body content in the iSRL three-column shell:
       - mobile header + hamburger
       - mobile nav drawer
       - .isrl-shell grid:
           .isrl-sidebar  (logo, collapsed nav, JS-built ToC)
           .ltx_page_main (original LaTeXML content, untouched)
           .isrl-right    (document metadata panel)
       - inline JS for nav toggle, hamburger, ToC active state
  7. Writes output to paper.published.html alongside the input file

Requirements: Python 3.8+, no third-party libraries.
"""

import sys
import re
import json
from datetime import datetime
from pathlib import Path


# ─── ANSI colour helpers ───────────────────────────────────────
R    = "\033[0;31m"
G    = "\033[0;32m"
Y    = "\033[0;33m"
B    = "\033[0;34m"
W    = "\033[0m"
BOLD = "\033[1m"


# ─── CLI helpers ──────────────────────────────────────────────
def ask(label: str, default: str = "", required: bool = True) -> str:
    hint = f" [{default}]" if default else ""
    while True:
        val = input(f"  {BOLD}{label}{W}{hint}: ").strip()
        if val:
            return val
        if default:
            return default
        if not required:
            return ""
        print(f"  {R}This field is required.{W}")


def pick(label: str, options: list) -> str:
    print(f"\n  {BOLD}{label}{W}")
    for i, opt in enumerate(options, 1):
        print(f"    {Y}{i}.{W} {opt}")
    while True:
        raw = input("  Enter number: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print(f"  {R}Enter a number 1–{len(options)}.{W}")


# ─── HTML extraction helpers ──────────────────────────────────
def strip_tags(html: str) -> str:
    """Remove all HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def extract_title(html: str) -> str:
    """Extract document title from ltx_title_document h1."""
    m = re.search(
        r'<h1[^>]*class="[^"]*ltx_title_document[^"]*"[^>]*>(.*?)</h1>',
        html, re.DOTALL | re.IGNORECASE
    )
    if m:
        return strip_tags(m.group(1))
    # fallback: <title>
    m2 = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    return strip_tags(m2.group(1)) if m2 else "iSRL Research Log"


def extract_abstract(html: str) -> str:
    """Extract plain-text abstract for meta description (max 300 chars)."""
    m = re.search(r'<div[^>]*class="[^"]*ltx_abstract[^"]*"[^>]*>(.*?)</div>',
                  html, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    # Skip the 'Abstract' label, take the first <p>
    para = re.search(r'<p[^>]*class="[^"]*ltx_p[^"]*"[^>]*>(.*?)</p>',
                     m.group(1), re.DOTALL | re.IGNORECASE)
    raw = strip_tags(para.group(1)) if para else strip_tags(m.group(1))
    return raw[:297] + "…" if len(raw) > 300 else raw


def extract_authors(html: str) -> list:
    """Extract author names from ltx_personname spans."""
    spans = re.findall(
        r'<span[^>]*class="[^"]*ltx_personname[^"]*"[^>]*>(.*?)</span>',
        html, re.DOTALL | re.IGNORECASE
    )
    authors = []
    for s in spans:
        # The first text node (before any <br> or nested span) is the name
        # Strip everything from the first <br> onwards
        clean = re.sub(r"<br[^>]*>.*", "", s, flags=re.DOTALL)
        name  = strip_tags(clean)
        if name:
            authors.append(name)
    return authors


def extract_date_str(html: str) -> str:
    """Extract date from ltx_dates div."""
    m = re.search(r'<div[^>]*class="[^"]*ltx_dates[^"]*"[^>]*>\(?(.*?)\)?<',
                  html, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def extract_sections(html: str) -> list:
    """
    Extract all h2 and h3 headings that have a parent element with an id.
    Returns list of dicts: {id, text, level}
    Used to build the sidebar ToC.
    """
    # Find all section/subsection openings: <section id="...">
    section_ids = {}
    for m in re.finditer(r'<(?:section|div)[^>]*\bid="([^"]+)"[^>]*>', html, re.IGNORECASE):
        section_ids[m.start()] = m.group(1)

    results = []
    heading_re = re.compile(
        r'<(h[23])[^>]*class="[^"]*ltx_title[^"]*"[^>]*>(.*?)</\1>',
        re.DOTALL | re.IGNORECASE
    )
    for hm in heading_re.finditer(html):
        tag     = hm.group(1).lower()
        level   = 2 if tag == "h2" else 3
        inner   = hm.group(2)
        text    = strip_tags(inner)
        # Remove leading "N " or "N.N " section numbering
        text    = re.sub(r"^\d+(\.\d+)*\s+", "", text)
        if not text:
            continue

        # Find the nearest preceding section id
        pos     = hm.start()
        nearest = ""
        best    = -1
        for spos, sid in section_ids.items():
            if spos <= pos and spos > best:
                best    = spos
                nearest = sid

        if nearest:
            results.append({"id": nearest, "text": text, "level": level})

    # Deduplicate (multiple headings can map to same section)
    seen = set()
    deduped = []
    for r in results:
        key = r["id"]
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    return deduped


# ─── Builder: SEO <head> ──────────────────────────────────────
def build_head(
    title: str,
    description: str,
    authors: list,
    doi: str,
    pub_date_iso: str,
    doc_type: str,
    canonical_url: str,
    zenodo_url: str,
) -> str:
    author_str   = ", ".join(authors) if authors else "iSRL"
    type_labels  = {"report": "Research Report", "paper": "Research Paper", "audit": "Adversarial Audit"}
    type_label   = type_labels.get(doc_type, "Research Output")
    kw_map       = {
        "report": "research report, Indian food informatics, IFID, iSRL, food classification, digital public infrastructure",
        "paper":  "research paper, systems architecture, open source, iSRL, public interest infrastructure",
        "audit":  "adversarial audit, red team analysis, iSRL, research critique, systems review",
    }
    keywords     = kw_map.get(doc_type, kw_map["report"])
    safe_title   = title.replace('"', '&quot;').replace("'", "&#39;")
    safe_desc    = description.replace('"', '&quot;').replace("'", "&#39;")

    # JSON-LD
    schema_types = {"report": "ScholarlyArticle", "paper": "ScholarlyArticle", "audit": "ScholarlyArticle"}
    schema_type  = schema_types.get(doc_type, "ScholarlyArticle")
    author_nodes = [
        {
            "@type": "Person",
            "name": a,
            "affiliation": {
                "@type": "Organization",
                "name": "Interdisciplinary Systems Research Lab (iSRL)",
                "url":  "https://isrl-research.github.io"
            }
        }
        for a in (authors or ["Lalitha A R"])
    ]
    ld = {
        "@context":          "https://schema.org",
        "@type":             schema_type,
        "name":              title,
        "headline":          title,
        "description":       description,
        "author":            author_nodes,
        "datePublished":     pub_date_iso,
        "publisher": {
            "@type": "Organization",
            "name":  "Interdisciplinary Systems Research Lab (iSRL)",
            "url":   "https://isrl-research.github.io"
        },
        "license":           "https://creativecommons.org/licenses/by/4.0/",
        "identifier":        doi,
        "url":               canonical_url,
        "sameAs":            zenodo_url,
        "isAccessibleForFree": True,
        "inLanguage":        "en",
        "isPartOf": {
            "@type": "Collection",
            "name":  "iSRL Research Logs",
            "url":   "https://isrl-research.github.io/logs/"
        }
    }
    ld_json = json.dumps(ld, indent=2, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{safe_title} — iSRL</title>

<!-- SEO core -->
<meta name="description" content="{safe_desc}">
<meta name="author" content="{author_str}">
<meta name="keywords" content="{keywords}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{canonical_url}">

<!-- Open Graph -->
<meta property="og:type" content="article">
<meta property="og:title" content="{safe_title} — iSRL">
<meta property="og:description" content="{safe_desc}">
<meta property="og:site_name" content="iSRL — Interdisciplinary Systems Research Lab">
<meta property="og:url" content="{canonical_url}">
<meta property="article:author" content="{author_str}">
<meta property="article:published_time" content="{pub_date_iso}">
<meta property="article:section" content="{type_label}">

<!-- Twitter -->
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{safe_title} — iSRL">
<meta name="twitter:description" content="{safe_desc}">

<!-- Dublin Core -->
<meta name="DC.title" content="{safe_title}">
<meta name="DC.creator" content="{author_str}">
<meta name="DC.date" content="{pub_date_iso}">
<meta name="DC.type" content="{type_label}">
<meta name="DC.identifier" content="{doi}">
<meta name="DC.publisher" content="Interdisciplinary Systems Research Lab (iSRL)">
<meta name="DC.rights" content="CC BY 4.0 International">

<!-- Google Scholar / citation indexing -->
<meta name="citation_title" content="{safe_title}">
<meta name="citation_author" content="{author_str}">
<meta name="citation_date" content="{pub_date_iso}">
<meta name="citation_doi" content="{doi}">
<meta name="citation_publisher" content="iSRL / Zenodo">
<meta name="citation_online_date" content="{pub_date_iso}">

<!-- JSON-LD structured data -->
<script type="application/ld+json">
{ld_json}
</script>

<!-- iSRL Research Log stylesheet (self-sufficient, no other CSS needed) -->
<link rel="stylesheet" href="res-log.css" type="text/css">
</head>"""


# ─── Builder: sidebar ToC HTML ────────────────────────────────
def build_toc_items(sections: list) -> str:
    if not sections:
        return '  <li><span style="font-family:\'DM Mono\',monospace;font-size:0.72rem;color:#5a5a57;">No sections found.</span></li>'
    lines = []
    for s in sections:
        css = "toc-h3" if s["level"] == 3 else "toc-h2"
        text = s["text"][:60] + "…" if len(s["text"]) > 60 else s["text"]
        lines.append(f'  <li class="{css}"><a href="#{s["id"]}">{text}</a></li>')
    return "\n".join(lines)


# ─── Builder: right sidebar metadata HTML ─────────────────────
def build_right_sidebar(
    doc_type: str,
    pub_date: str,
    doi: str,
    zenodo_url: str,
    authors: list,
) -> str:
    type_labels = {"report": "Report", "paper": "Paper", "audit": "Audit"}
    type_label  = type_labels.get(doc_type, "Research Output")
    author_html = "\n".join(
        f"        {a}<br>" for a in (authors or ["Lalitha A R"])
    )
    return f"""
  <aside class="isrl-right" aria-label="Document metadata">

    <div class="isrl-right-section">
      <span class="isrl-right-label">Document</span>
      <div class="isrl-right-meta">
        <strong>{type_label}</strong>
        {author_html}
        <br>
        {pub_date}
      </div>
    </div>

    <div class="isrl-right-section">
      <span class="isrl-right-label">Archive</span>
      <div class="isrl-right-meta">
        <a href="{zenodo_url}" target="_blank" rel="noopener noreferrer">
          View on Zenodo →
        </a>
        <br>
        <span class="meta-doi">{doi}</span>
      </div>
    </div>

    <div class="isrl-right-section">
      <span class="isrl-right-label">Project</span>
      <div class="isrl-right-meta">
        <a href="https://isrl-research.github.io/ifid.html">Indian Food Informatics Data</a><br>
        IFID 2026
      </div>
    </div>

    <div class="isrl-right-section">
      <span class="isrl-right-label">License</span>
      <div class="isrl-right-meta">
        <a href="https://creativecommons.org/licenses/by/4.0/"
           target="_blank" rel="noopener noreferrer">
          CC BY 4.0 International
        </a><br>
        Data is a permanent public asset.
      </div>
    </div>

    <div class="isrl-right-footer">
      <p>CC BY 4.0 International<br>iSRL / Digital Public Infrastructure</p>
    </div>

  </aside>"""


# ─── Builder: full body ───────────────────────────────────────
def build_body(
    original_body_content: str,
    doc_type: str,
    pub_date: str,
    doi: str,
    zenodo_url: str,
    authors: list,
    toc_items: str,
) -> str:
    type_labels = {"report": "Report", "paper": "Paper", "audit": "Audit"}
    type_label  = type_labels.get(doc_type, "Research Output")
    right       = build_right_sidebar(doc_type, pub_date, doi, zenodo_url, authors)

    return f"""<body>

<a href="#isrl-main" class="isrl-skip-link">Skip to main content</a>

<!-- ── Mobile header ── -->
<header class="isrl-mobile-header" role="banner">
  <a href="/" class="isrl-mobile-logo" aria-label="iSRL home">
    <span class="logo-i">i</span>SRL
  </a>
  <button
    class="isrl-hamburger"
    id="isrl-hamburger"
    aria-label="Open navigation"
    aria-expanded="false"
    aria-controls="isrl-mobile-drawer">
    <span></span><span></span><span></span>
  </button>
</header>

<!-- ── Mobile nav drawer ── -->
<nav
  class="isrl-mobile-drawer"
  id="isrl-mobile-drawer"
  aria-label="Mobile navigation"
  aria-hidden="true">
  <a href="/" class="isrl-mobile-drawer-logo" aria-label="iSRL home">
    <span class="logo-i">i</span>SRL
  </a>
  <ul class="isrl-nav-list" role="list">
    <li><a href="/logs/">Research Logs</a></li>
    <li><a href="/ifid.html">IFID</a></li>
    <li><a href="/about.html">About</a></li>
    <li><a href="/join-us.html">Join Us</a></li>
    <li><a href="/funding.html">Funding</a></li>
  </ul>
</nav>

<!-- ── Three-column shell ── -->
<div class="isrl-shell">

  <!-- Left sidebar -->
  <aside class="isrl-sidebar" aria-label="Site and document navigation">

    <div class="isrl-logo-block">
      <span class="isrl-logo-rule" aria-hidden="true"></span>
      <a href="/" class="isrl-logo-wordmark" aria-label="iSRL home">
        <span class="logo-i">i</span>SRL
      </a>
      <span class="isrl-logo-sub">Systemic Infrastructure</span>
    </div>

    <!-- Main nav collapsed by default -->
    <nav aria-label="Primary navigation">
      <button
        class="isrl-nav-toggle"
        aria-expanded="false"
        aria-controls="isrl-nav-panel"
        id="isrl-nav-toggle">
        <span class="isrl-nav-arrow" aria-hidden="true">▶</span>
        Index
      </button>
      <div class="isrl-nav-panel" id="isrl-nav-panel">
        <ul class="isrl-nav-list" role="list">
          <li><a href="/logs/">Research Logs</a></li>
          <li><a href="/ifid.html">IFID</a></li>
          <li><a href="/about.html">About</a></li>
          <li><a href="/join-us.html">Join Us</a></li>
          <li><a href="/funding.html">Funding</a></li>
        </ul>
      </div>
    </nav>

    <div class="isrl-toc-divider" aria-hidden="true"></div>

    <!-- Table of contents (static from extraction + enhanced by JS) -->
    <nav class="isrl-toc-wrap" aria-label="Table of contents">
      <span class="isrl-toc-label">Contents</span>
      <ul class="isrl-toc" id="isrl-toc" role="list">
{toc_items}
      </ul>
    </nav>

    <div class="isrl-sidebar-footer">
      <p>CC BY 4.0 International<br>Data is a permanent public asset<br>iSRL / Digital Public Infrastructure</p>
    </div>

  </aside>

  <!-- Main content: original LaTeXML output, unchanged -->
  <main id="isrl-main" aria-label="Research log">
    <span class="isrl-doc-badge" data-type="{doc_type}">{type_label}</span>
    {original_body_content}
  </main>

  <!-- Right sidebar: document metadata -->
{right}

</div><!-- /.isrl-shell -->


<script>
/* ── Nav toggle ─────────────────────────────────────────────── */
(function () {{
  var btn   = document.getElementById('isrl-nav-toggle');
  var panel = document.getElementById('isrl-nav-panel');
  if (!btn || !panel) return;
  btn.addEventListener('click', function () {{
    var open = panel.classList.toggle('open');
    btn.setAttribute('aria-expanded', String(open));
  }});
}})();

/* ── Mobile hamburger ────────────────────────────────────────── */
(function () {{
  var hambtn = document.getElementById('isrl-hamburger');
  var drawer = document.getElementById('isrl-mobile-drawer');
  if (!hambtn || !drawer) return;

  function close() {{
    hambtn.setAttribute('aria-expanded', 'false');
    hambtn.setAttribute('aria-label', 'Open navigation');
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
  }}

  hambtn.addEventListener('click', function () {{
    var expanded = hambtn.getAttribute('aria-expanded') === 'true';
    if (expanded) {{
      close();
    }} else {{
      hambtn.setAttribute('aria-expanded', 'true');
      hambtn.setAttribute('aria-label', 'Close navigation');
      drawer.classList.add('open');
      drawer.setAttribute('aria-hidden', 'false');
      var first = drawer.querySelector('a');
      if (first) first.focus();
    }}
  }});

  document.addEventListener('keydown', function (e) {{
    if (e.key === 'Escape' && drawer.classList.contains('open')) {{
      close();
      hambtn.focus();
    }}
  }});

  drawer.querySelectorAll('a').forEach(function (l) {{
    l.addEventListener('click', close);
  }});
}})();

/* ── ToC active state on scroll ─────────────────────────────── */
(function () {{
  var links = document.querySelectorAll('#isrl-toc a');
  if (!links.length) return;

  var targets = Array.from(links).map(function (a) {{
    var id = a.getAttribute('href').replace('#', '');
    return {{ el: document.getElementById(id), link: a }};
  }}).filter(function (t) {{ return t.el; }});

  if (!targets.length) return;

  var io = new IntersectionObserver(function (entries) {{
    entries.forEach(function (entry) {{
      var match = targets.find(function (t) {{ return t.el === entry.target; }});
      if (match) {{
        if (entry.isIntersecting) {{
          match.link.classList.add('toc-active');
        }} else {{
          match.link.classList.remove('toc-active');
        }}
      }}
    }});
  }}, {{ rootMargin: '0px 0px -55% 0px', threshold: 0 }});

  targets.forEach(function (t) {{ io.observe(t.el); }});
}})();
</script>

</body>
</html>"""


# ─── Date normalisation ────────────────────────────────────────
def normalise_date(raw: str) -> str:
    """Try to return an ISO date string; fallback to raw."""
    for fmt in ("%B %d, %Y", "%B %Y", "%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime(
                "%Y-%m-%d" if "%d" in fmt else "%Y-%m"
            )
        except ValueError:
            continue
    return raw.strip()


# ─── Main ──────────────────────────────────────────────────────
def main():
    print(f"\n{BOLD}iSRL Research Log Publisher{W}")
    print("─" * 42)

    if len(sys.argv) < 2:
        print(f"{R}Usage: python3 isrl-publish.py path/to/paper.html{W}\n")
        sys.exit(1)

    source = Path(sys.argv[1])
    if not source.exists():
        print(f"{R}File not found: {source}{W}\n")
        sys.exit(1)

    html = source.read_text(encoding="utf-8")
    print(f"{G}✓ Loaded:{W} {source.name}  ({len(html):,} chars)")

    # ── Extract metadata from LaTeXML output ──
    title    = extract_title(html)
    abstract = extract_abstract(html)
    authors  = extract_authors(html)
    raw_date = extract_date_str(html)
    sections = extract_sections(html)

    print(f"\n{B}Auto-detected:{W}")
    print(f"  Title:    {title[:72]}{'…' if len(title) > 72 else ''}")
    print(f"  Authors:  {', '.join(authors) if authors else '(none)'}")
    print(f"  Date:     {raw_date or '(none)'}")
    print(f"  Sections: {len(sections)} heading(s) found for ToC")

    # ── Prompt for publication metadata ──
    print(f"\n{B}Publication metadata:{W}")
    doi      = ask("Zenodo DOI  (e.g. 10.5281/zenodo.12345678)")
    zenodo   = f"https://doi.org/{doi}"
    pub_date = ask("Publication date  (e.g. 'February 2026' or '2026-02-19')",
                   default=raw_date or datetime.today().strftime("%Y-%m-%d"))
    pub_iso  = normalise_date(pub_date)
    doc_type = pick("Document type", ["report", "paper", "audit"])

    slug     = re.sub(r"[^a-z0-9]+", "-", source.stem.lower()).strip("-")
    canon    = ask(
        "Canonical URL",
        default=f"https://isrl-research.github.io/logs/{slug}/"
    )

    # ── Build output ──
    print(f"\n{B}Building…{W}")

    # Extract everything inside <body>...</body>
    # Use string positions to avoid regex catastrophic backtracking on base64
    body_open_m = re.search(r"<body[^>]*>", html, re.IGNORECASE)
    if not body_open_m:
        print(f"{R}No <body> tag found.{W}")
        sys.exit(1)

    content_start = body_open_m.end()
    # rfind is safe: finds last occurrence without backtracking
    body_close_idx = html.lower().rfind("</body>")
    if body_close_idx == -1:
        # Truncated file — take everything after <body>
        original_content = html[content_start:].strip()
    else:
        original_content = html[content_start:body_close_idx].strip()

    toc_items = build_toc_items(sections)

    new_head = build_head(
        title        = title,
        description  = abstract,
        authors      = authors,
        doi          = doi,
        pub_date_iso = pub_iso,
        doc_type     = doc_type,
        canonical_url= canon,
        zenodo_url   = zenodo,
    )

    new_body = build_body(
        original_body_content = original_content,
        doc_type   = doc_type,
        pub_date   = pub_date,
        doi        = doi,
        zenodo_url = zenodo,
        authors    = authors,
        toc_items  = toc_items,
    )

    output = new_head + "\n" + new_body

    # ── Write ──
    out_path = source.parent / f"{source.stem}.published.html"
    out_path.write_text(output, encoding="utf-8")

    print(f"\n{G}{'─' * 42}")
    print(f"✓ Published:  {out_path}")
    print(f"  DOI:        {doi}")
    print(f"  Type:       {doc_type}")
    print(f"  Date:       {pub_date}  →  ISO: {pub_iso}")
    print(f"  ToC:        {len(sections)} section(s) injected")
    print(f"  Output:     {len(output):,} chars")
    print(f"{'─' * 42}{W}")
    print(f"\n  {Y}Next step:{W} place res-log.css alongside the output HTML,")
    print(f"  or update the stylesheet href to your assets path.\n")


if __name__ == "__main__":
    main()
