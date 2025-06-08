# transaction_tracker/core/categorizer.py
def categorize(tx, categories_map):
    name = tx.merchant.lower()
    for cat, keywords in categories_map.items():
        for kw in keywords:
            if kw.lower() in name:
                return cat
    return None