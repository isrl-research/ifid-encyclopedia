#!/usr/bin/env python3
"""
Delete entries marked as 'delete' in the v0.1-v0.2 audit CSV
from JSON, LaTeX, and Markdown files in data/v020/.
"""

import json
import os
import re
import glob

BASE = os.path.join(os.path.dirname(__file__), '..', 'data')
V020 = os.path.join(BASE, 'v020')

DELETE_SLUGS = [
    "acidity-regulator",
    "anticaking-agent",
    "antioxidant",
    "bread-improvers",
    "capsule-shell",
    "color-generic",
    "dry-fruit",
    "fat",
    "fiber",
    "fillers",
    "flavour-enhancer",
    "flavouring",
    "flour-treatment-agent",
    "flour",
    "foam-stabilizer",
    "fruit-flavouring",
    "fruit-juice",
    "fruit",
    "glazing-agent",
    "humectant",
    "juice-concentrate",
    "milk-components",
    "milk-products",
    "minerals",
    "multigrain",
    "multivitamins",
    "pulses",
    "satva",
    "seasoning",
    "seeds",
    "shortening",
    "stabilizer",
    "supergrain",
    "sweetener",
    "tenderizer",
    "thickener",
    "vitamins",
    "whole-grains",
]


def delete_from_json():
    """Remove entries from the JSON file and update metadata."""
    json_path = os.path.join(V020, 'ifid_encyclopedia_v020.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    deleted_count = 0
    slug_set = set(DELETE_SLUGS)

    for category_name, ingredients in data['data'].items():
        keys_to_delete = []
        for ingredient_name, ingredient_data in ingredients.items():
            if ingredient_data.get('slug') in slug_set:
                keys_to_delete.append(ingredient_name)
        for key in keys_to_delete:
            del ingredients[key]
            deleted_count += 1
            print(f"  JSON: Deleted '{key}' (slug: {data.get('_deleted_slug', 'n/a')}) from '{category_name}'")

    # Update statistics
    old_count = data['statistics']['total_ingredients']
    data['statistics']['total_ingredients'] = old_count - deleted_count

    # Update version
    data['metadata']['version'] = '0.2.0-alpha'

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"\n  JSON: Deleted {deleted_count} entries. Count: {old_count} -> {old_count - deleted_count}")
    return deleted_count


def delete_from_latex():
    """Remove section blocks from the LaTeX file for deleted slugs."""
    tex_path = os.path.join(V020, 'latex', 'ency.tex')
    with open(tex_path, 'r', encoding='utf-8') as f:
        content = f.read()

    slug_set = set(DELETE_SLUGS)
    deleted_count = 0

    # Strategy: split into sections based on \newpage, then filter out
    # sections whose Technical Profile contains a deleted slug.
    # Each entry follows the pattern:
    #   \section*{Name}
    #   ... content ...
    #   \item[Slug] \texttt{<slug>}
    #   ... 
    #   \newpage

    # Split on \newpage to get individual blocks
    # But we need to be careful about the preamble (before first \section*)
    
    # Find the first \section* to separate preamble
    first_section = content.find('\\section*{')
    if first_section == -1:
        print("  LaTeX: No sections found!")
        return 0

    preamble = content[:first_section]
    body = content[first_section:]

    # Split body into blocks. Each block ends with \newpage
    # Use regex to split into section blocks
    # Pattern: from \section*{ to (but not including) the next \section*{ or \part{ or end of file
    # Actually, each section ends with \newpage, so let's split on \newpage
    
    blocks = re.split(r'(\\newpage\n)', body)
    
    # Reconstruct into section blocks (content + \newpage pairs)
    sections = []
    i = 0
    while i < len(blocks):
        if i + 1 < len(blocks) and blocks[i + 1].strip() == '\\newpage':
            sections.append(blocks[i] + blocks[i + 1])
            i += 2
        else:
            sections.append(blocks[i])
            i += 1

    # Filter out sections containing deleted slugs
    kept_sections = []
    for section in sections:
        # Check if this section contains a slug we need to delete
        slug_match = re.search(r'\\item\[Slug\]\s*\\texttt\{([^}]+)\}', section)
        if slug_match:
            slug = slug_match.group(1)
            if slug in slug_set:
                deleted_count += 1
                print(f"  LaTeX: Deleted section with slug '{slug}'")
                continue
        kept_sections.append(section)

    new_content = preamble + ''.join(kept_sections)

    with open(tex_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"\n  LaTeX: Deleted {deleted_count} sections.")
    return deleted_count


def delete_md_files():
    """Delete individual .md files for deleted slugs."""
    md_base = os.path.join(V020, 'md')
    deleted_count = 0

    for slug in DELETE_SLUGS:
        # Search across all category subdirectories
        pattern = os.path.join(md_base, '**', f'{slug}.md')
        matches = glob.glob(pattern, recursive=True)
        if matches:
            for match in matches:
                os.remove(match)
                deleted_count += 1
                print(f"  MD: Deleted '{os.path.relpath(match, md_base)}'")
        else:
            print(f"  MD: WARNING - No file found for slug '{slug}'")

    print(f"\n  MD: Deleted {deleted_count} files.")
    return deleted_count


if __name__ == '__main__':
    print("=" * 60)
    print("Deleting audit-flagged entries from v020 data")
    print("=" * 60)

    print("\n--- JSON ---")
    json_count = delete_from_json()

    print("\n--- LaTeX ---")
    tex_count = delete_from_latex()

    print("\n--- Markdown ---")
    md_count = delete_md_files()

    print("\n" + "=" * 60)
    print(f"Summary: JSON={json_count}, LaTeX={tex_count}, MD={md_count}")
    print("=" * 60)
