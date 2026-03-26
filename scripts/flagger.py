import os
import pandas as pd
import difflib

# --- CONFIGURATION ---
DB_FILE = "v0.1-v0.2_audit.csv"

def load_db():
    """Purely loads the CSV file. No disk syncing or extra logic."""
    if not os.path.exists(DB_FILE):
        print(f"❌ Error: {DB_FILE} not found.")
        return None
    
    df = pd.read_csv(DB_FILE)
    # Ensure slug column is treated as string to prevent search errors
    df['canon-slug'] = df['canon-slug'].astype(str)
    return df

def main():
    df = load_db()
    if df is None or df.empty:
        return

    print("\n--- Bulk Encyclopedia Auditor (CSV Search) ---")
    print("Tip: Enter ingredients separated by commas (e.g., fat, flour, fiber)")

    while True:
        raw_input = input("\nEnter ingredient(s) (or 'q' to quit): ").strip()
        if raw_input.lower() == 'q': 
            break
        if not raw_input: 
            continue

        queries = [q.strip() for q in raw_input.split(',') if q.strip()]
        selected_targets = []

        # 1. Selection Phase: Search purely in the CSV's 'canon-slug' column
        for q in queries:
            all_slugs = df['canon-slug'].tolist()
            # Uses difflib to find matches within the existing CSV rows
            matches = difflib.get_close_matches(q, all_slugs, n=10, cutoff=0.1)

            if not matches:
                print(f"❌ No matches found for '{q}'")
                continue

            print(f"\nResults for '{q}':")
            for i, m in enumerate(matches):
                # Locates the existing row data for the match
                curr = df.loc[df['canon-slug'] == m].iloc[0]
                print(f"[{i}] {m:<35} | {curr['status']:<8} | {curr['note']}")

            choice = input(f"Select index for '{q}' (or 's' to skip): ")
            if choice.isdigit() and int(choice) < len(matches):
                selected_targets.append(matches[int(choice)])

        if not selected_targets:
            print("No items selected for update.")
            continue

        # 2. Bulk Action Phase (Existing CLI UI)
        print(f"\nSelected items: {selected_targets}")
        print("Apply to all: [a] Approve, [f] Flag, [m] Merge, [d] Delete")
        action = input("Choose action: ").lower()

        status, note = None, None

        if action == 'f':
            status = "flag"
            note = input("Reason for flag: ")
        elif action == 'd':
            status = "delete"
            note = input("Reason for delete: ")
        elif action == 'm':
            status = "merge"
            target = input("Merge all into (slug name): ")
            note = f"MERGE INTO {target}"
        elif action == 'a':
            status = "approve"
            note = "NONE"
        else:
            print("Skipping bulk update.")
            continue

        # 3. Batch Update: Writes results back to the CSV
        if status:
            for slug in selected_targets:
                df.loc[df['canon-slug'] == slug, 'status'] = status
                df.loc[df['canon-slug'] == slug, 'note'] = note

            df.to_csv(DB_FILE, index=False)
            print(f"✅ Batch updated {len(selected_targets)} items to {status.upper()}.")

if __name__ == "__main__":
    main()
