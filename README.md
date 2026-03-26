# Encyclopedia of Indian Food Ingredients

**Version:** v2.0 (IFID v0.2.0-alpha)
**DOI:** [10.5281/zenodo.18650862](https://doi.org/10.5281/zenodo.18650862)
**License:** [Open Data Commons Attribution License (ODC-By)](https://opendatacommons.org/licenses/by/)
**Author:** Lalitha A R · [Interdisciplinary Systems Research Lab (iSRL)](https://isrl-research.github.io/)

---

## Overview

The **Encyclopedia of Indian Food Ingredients** is a core output of the **Indian Food Informatics Data (IFID)** project. It provides a standardized taxonomy and structured descriptions for **623 food components** found in the Indian food ecosystem — from traditional Ayurvedic botanicals and regional spices to modern industrial food additives.

Each ingredient is documented across four dimensions:

| Field | Description |
|---|---|
| `history_and_sourcing` | Origin, cultivation, and historical use in India |
| `culinary_usage_home` | How the ingredient appears in domestic cooking |
| `industrial_applications` | Role in packaged food manufacturing |
| `distinction_and_confusion` | How to distinguish it from similar ingredients |

---

## Repository Structure

```
encyclopedia/
├── data/
│   ├── v010/                       # v0.1.0 archive (JSON + MD + LaTeX)
│   ├── v020/                       # v0.2.0 intermediate build
│   ├── v030/
│   │   └── ifid_encyclopedia_v020.json   # ← source of truth (623 ingredients)
│   └── v0.1-v0.2_audit.csv         # taxonomy audit log
├── quarto/                         # Quarto project (HTML website + PDF book)
│   ├── _quarto.yml                 # website config
│   ├── _quarto-book.yml            # PDF book config
│   ├── custom.scss                 # iSRL brand styles
│   ├── index.qmd                   # main landing page
│   └── {category}/
│       ├── index.qmd               # category listing page
│       └── {slug}.qmd              # ingredient page (×623)
└── scripts/
    ├── generate_qmd.py             # ← primary pipeline: JSON → .qmd
    ├── build_encyclopedia.py       # old pipeline (HTML via pandoc), archived
    ├── delete_entries.py           # utility: remove entries from JSON
    ├── flagger.py                  # v0.1→v0.2 audit tool
    ├── interlink.py                # old interlinking reference
    └── slug_list.py                # full slug list constant
```

---

## Data

### Source of Truth

`data/v030/ifid_encyclopedia_v020.json`

```json
{
  "metadata": {
    "title": "Encyclopedia of Indian Food Ingredients",
    "version": "0.2.0-alpha",
    "release_date": "2026-02-25",
    "doi": "https://doi.org/10.5281/zenodo.18650862",
    "license": "Open Data Commons Attribution License (ODC-By)",
    "author": "Lalitha A R",
    "institution": "Interdisciplinary Systems Research Lab (iSRL)"
  },
  "statistics": {
    "total_categories": 8,
    "total_ingredients": 623
  },
  "data": {
    "Additives & Functional": {
      "Acetic Acid (INS 260)": {
        "slug": "acetic-acid-ins-260",
        "json": {
          "ingredient_name": "Acetic Acid (INS 260)",
          "category": "Additives & Functional",
          "description": {
            "history_and_sourcing": "...",
            "culinary_usage_home": "...",
            "industrial_applications": "...",
            "distinction_and_confusion": "..."
          },
          "keywords": ["Acetic acid", "INS 260", "Acidity regulator"]
        }
      }
    }
  }
}
```

### Categories

| Category | Slug | Count |
|---|---|---|
| Additives & Functional | `additives-functional` | 263 |
| Fruits, Veg & Botanicals | `fruits-veg-botanicals` | 164 |
| Spices & Seasonings | `spices-seasonings` | 68 |
| Staples (Grains/Dals) | `staples` | 41 |
| Oils & Fats | `oils-fats` | 36 |
| Dairy & Alternatives | `dairy-alternatives` | 23 |
| Sweeteners | `sweeteners` | 18 |
| Proteins & Meats | `proteins-meats` | 10 |

---

## Pipeline

### Render HTML website

```bash
cd quarto/
quarto render
# Output: quarto/_site/index.html
```

### Render PDF book

```bash
cd quarto/
quarto render --config _quarto-book.yml
# Output: quarto/_book/
```

### Regenerate all .qmd source files

```bash
python3 scripts/generate_qmd.py
# Reads: data/v030/ifid_encyclopedia_v020.json
# Writes: quarto/ (all 632 .qmd files + configs)
```

---

## Usage

### For AI / RAG Developers

The JSON is structured for direct ingestion into vector databases. Each ingredient entry has a clean slug, flat keyword list, and four prose fields — no HTML, no cross-link corruption.

Parse with:
```python
import json

with open("data/v030/ifid_encyclopedia_v020.json") as f:
    data = json.load(f)

for cat_name, items in data["data"].items():
    for ing_name, ing_data in items.items():
        slug = ing_data["slug"]
        desc = ing_data["json"]["description"]
        keywords = ing_data["json"]["keywords"]
```

### For Knowledge Graph Construction

The dataset includes first-occurrence cross-links between ingredient pages, resolving to `{category}/{slug}.qmd`. The `SKIP_SLUGS` list (25 high-frequency terms) is excluded from interlinking. Approximately 4,000+ internal links across the corpus.

---

## Citation

### APA 7th Edition
```
Lalitha, A. R. (2026). Encyclopedia of Indian Food Ingredients (v2.0).
Interdisciplinary Systems Research Lab (iSRL).
https://doi.org/10.5281/zenodo.18650862
```

### BibTeX
```bibtex
@misc{Lalitha2026IFID,
  author       = {Lalitha, A. R.},
  title        = {Encyclopedia of Indian Food Ingredients (v2.0)},
  year         = {2026},
  publisher    = {Interdisciplinary Systems Research Lab (iSRL)},
  doi          = {10.5281/zenodo.18650862},
  url          = {https://doi.org/10.5281/zenodo.18650862}
}
```

---

## License

This dataset is released under the **Open Data Commons Attribution License (ODC-By)**. You are free to share, use, and adapt the data, provided you credit the original author and the IFID project.

## Contact

Maintained by the **Interdisciplinary Systems Research Lab (iSRL)**.
- Lab: [isrl-research.github.io](https://isrl-research.github.io/)
- Issues: GitHub issue tracker
