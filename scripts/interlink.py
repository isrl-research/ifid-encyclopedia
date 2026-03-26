import pandas as pd
import os
import re

# --- CONFIGURATION ---
CSV_FILE = "v0.1-v0.2_audit.csv"
MD_DIR = "data/md"  # The directory where your .md files live

def calculate_strict_potential():
    if not os.path.exists(CSV_FILE):
        print(f"❌ Error: {CSV_FILE} not found.")
        return

    # 1. Load and filter for 'approve'
    df = pd.read_csv(CSV_FILE)
    # Ensure consistency in slug naming
    approved_df = df[df['status'].str.lower() == 'approve'].copy()
    
    # Get unique list of approved slugs
    # We sort by length descending to ensure 'wheat-flour' is checked before 'wheat'
    approved_slugs = sorted(list(set(approved_df['canon-slug'].astype(str).tolist())), key=len, reverse=True)
    
    total_approved = len(approved_slugs)
    
    # Track incoming links: {target_slug: count_of_unique_source_files}
    incoming_link_counts = {slug: 0 for slug in approved_slugs}
    total_link_edges = 0

    print(f"📊 Total Approved Ingredients: {total_approved}")
    print(f"🔍 Scanning files in {MD_DIR} for unique interlinks...")

    # 2. Iterate through each approved file (The "Source")
    for source_slug in approved_slugs:
        # Standardize filename (handle .md suffix if present in slug or not)
        clean_name = source_slug if source_slug.endswith(".md") else f"{source_slug}.md"
        
        # Locate the file (walking subdirectories if necessary)
        filepath = None
        for root, dirs, files in os.walk(MD_DIR):
            if clean_name in files:
                filepath = os.path.join(root, clean_name)
                break
        
        if not filepath:
            continue

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().lower()
            
            # 3. Check for every OTHER approved slug in this specific file
            for target_slug in approved_slugs:
                if target_slug == source_slug:
                    continue
                
                # Convert slug to a natural search phrase (e.g., 'watermelon-seeds' -> 'watermelon seeds')
                search_phrase = target_slug.replace(".md", "").replace("-", " ")
                
                # Use regex for word boundaries to avoid partial matches (e.g., 'pea' matching 'pearl')
                pattern = rf"\b{re.escape(search_phrase)}\b"
                
                if re.search(pattern, content):
                    # Found a link! Because we are in a loop over target_slugs 
                    # for ONE source file, this naturally ensures NO double counting
                    # of the same target within this file.
                    incoming_link_counts[target_slug] += 1
                    total_link_edges += 1
                    
        except Exception as e:
            print(f"⚠️ Could not read {source_slug}: {e}")

    # 4. Final Reporting
    print("\n" + "="*55)
    print(f"📈 INTERLINK POTENTIAL REPORT")
    print("="*55)
    print(f"{'Total Approved Ingredients':<35} : {total_approved}")
    print(f"{'Total Unique Interlink Edges':<35} : {total_link_edges}")
    print(f"{'Average Links Per Ingredient':<35} : {total_link_edges/total_approved:.2f}")
    print("-" * 55)
    
    # Top 20 Ranking
    sorted_links = sorted(incoming_link_counts.items(), key=lambda x: x[1], reverse=True)
    
    print(f"{'Top 20 Power Nodes (Slugs)':<35} | {'Incoming Links'}")
    print("-" * 55)
    for slug, count in sorted_links[:20]:
        print(f"{slug.replace('.md', ''):<35} | {count}")
    print("="*55)

if __name__ == "__main__":
    calculate_strict_potential()
