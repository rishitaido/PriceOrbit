import asyncio
import csv
import re
from difflib import SequenceMatcher
from pathlib import Path

from dotenv import load_dotenv

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.product_model import Product
from app.services.kroger_service import KrogerService

# Environment Setup
base_dir = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=base_dir / ".env")


def get_confidence(a, b):
    """Calculates how similar two strings are (0 - 100.0)"""
    return round(SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100, 1)


def kroger_safe_query(value: str, max_words: int = 8) -> str:
    """
    Kroger product search accepts a max of 8 words per term.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""

    base = re.sub(r"\s*\([^)]*\)\s*$", "", raw)
    base = re.sub(r"[^0-9A-Za-z\s]+", " ", base)
    words = [word for word in re.split(r"\s+", base.strip()) if word]
    if not words:
        return ""
    return " ".join(words[: max(1, max_words)])

async def map_products():
    # Initialize the Service with keys from your .env
    # Service needs the client_id and secret
    kroger = KrogerService(
        client_id=settings.KROGER_CLIENT_ID,
        client_secret=settings.KROGER_CLIENT_SECRET
    )
    
    db = SessionLocal()
    unmapped = []
    mapped_count = 0
    manual_needed = 0

    try:
        # Fetch only products missing a Kroger ID
        products = db.query(Product).filter(Product.kroger_product_id.is_(None)).all()
        print(f"--- PriceOrbit: Mapping {len(products)} products ---\n")

        for product in products:
            print(f"Searching for: {product.name}...")
            query = kroger_safe_query(product.name)
            if not query:
                print(f"No usable query for: {product.name}")
                unmapped.append({"name": product.name, "reason": "Invalid search query"})
                manual_needed += 1
                continue
            
            try:
                # Call asynch search
                results = await kroger.search_products(query, limit=3)
            except Exception as e:
                print(f"API Connection Error: {e}")
                continue

            if not results:
                print(f"No match found: {product.name}")
                unmapped.append({"name": product.name, "reason": "No API results"})
                manual_needed += 1
            
            # High Confidence Match (if possible, otherwise manual review)
            elif get_confidence(product.name, results[0]['description']) > 90:
                match = results[0]
                conf = get_confidence(product.name, match['description'])
                
                product.kroger_product_id = match['productId']
                if match.get('images'):
                    product.image_url = match['images'][0]['sizes'][-1]['url']
                
                db.commit()
                print(f"Mapped: {product.name} -> {match['productId']} ({conf}%)")
                mapped_count += 1

            # Manual review
            else:
                print(f"Ambiguous matches for '{product.name}':")
                for i, res in enumerate(results, 1):
                    conf = get_confidence(product.name, res['description'])
                    print(f"    {i}. {res['description']} (ID: {res['productId']}) - {conf}%")
                
                choice = input(f"    Choose [1-{len(results)}/s (skip)]: ").strip().lower()
                
                if choice.isdigit() and 1 <= int(choice) <= len(results):
                    match = results[int(choice)-1]
                    product.kroger_product_id = match['productId']
                    if match.get('images'):
                        product.image_url = match['images'][0]['sizes'][-1]['url']
                    db.commit()
                    print(f"Manually Mapped: {product.name}")
                    mapped_count += 1
                else:
                    print(f"Skipped: {product.name}")
                    unmapped.append({"name": product.name, "reason": "Manual skip/Ambiguous"})
                    manual_needed += 1

            # 2 seconds per product limit to respect API rate limits
            await asyncio.sleep(2)

    finally:
        # Generate the CSV Report
        if unmapped:
            with open('unmapped_products.csv', 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=["name", "reason"])
                writer.writeheader()
                writer.writerows(unmapped)
        
        await kroger.aclose()
        db.close()
        
        print("\n" + "="*30)
        print("SUMMARY:")
        print(f"Successfully Mapped: {mapped_count}")
        print(f"Manual Review Needed: {manual_needed}")
        print("="*30)

if __name__ == "__main__":
    # Start the async event loop
    asyncio.run(map_products())
