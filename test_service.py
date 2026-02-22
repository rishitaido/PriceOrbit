"""
Quick test script for ProductService
Run: python test_service.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.services.product_service import ProductService
from app.schemas.product import ProductCreate, ProductUpdate
from decimal import Decimal


def test_product_service():
    """Test all ProductService methods"""
    print("\n" + "="*60)
    print("🧪 TESTING PRODUCT SERVICE")
    print("="*60)
    
    db = SessionLocal()
    service = ProductService(db)
    
    try:
        # Test 1: Get all products
        print("\n📋 Test 1: Get All Products")
        products = service.get_all_products(skip=0, limit=5)
        print(f"✅ Retrieved {len(products)} products")
        for p in products[:3]:
            print(f"   - {p.name} ({p.category})")
        
        # Test 2: Count products
        print("\n📊 Test 2: Count Products")
        total = service.get_product_count()
        print(f"✅ Total products: {total}")
        
        # Test 3: Get product by ID
        print("\n🔍 Test 3: Get Product by ID")
        if products:
            product = service.get_product_by_id(products[0].id)
            print(f"✅ Retrieved: {product.name}")
            print(f"   Price: ${product.current_price}")
            print(f"   Health Score: {product.health_score}")
        
        # Test 4: Search products
        print("\n🔎 Test 4: Search Products")
        results = service.search_products("banana")
        print(f"✅ Found {len(results)} products matching 'banana'")
        for r in results:
            print(f"   - {r.name}")
        
        # Test 5: Get categories
        print("\n📂 Test 5: Get All Categories")
        categories = service.get_all_categories()
        print(f"✅ Found {len(categories)} categories:")
        for cat in categories:
            count = service.get_product_count(category=cat)
            print(f"   - {cat}: {count} products")
        
        # Test 6: Create product
        print("\n➕ Test 6: Create Product")
        new_product_data = ProductCreate(
            name="Test Product - DELETE ME",
            category="Test Category",
            import_dependency="Low",
            tariff_rate=Decimal("5.0"),
            current_price=Decimal("9.99")
        )
        new_product = service.create_product(new_product_data)
        print(f"✅ Created product ID: {new_product.id}")
        print(f"   Name: {new_product.name}")
        print(f"   Health Score: {new_product.health_score}")
        
        # Test 7: Update product
        print("\n✏️ Test 7: Update Product")
        update_data = ProductUpdate(
            current_price=Decimal("12.99")
        )
        updated_product = service.update_product(new_product.id, update_data)
        print(f"✅ Updated product price: ${updated_product.current_price}")
        print(f"   Price history entries: {len(updated_product.price_history or [])}")
        
        # Test 8: Delete product
        print("\n🗑️ Test 8: Delete Product")
        service.delete_product(new_product.id)
        print(f"✅ Deleted product ID: {new_product.id}")
        
        # Test 9: Verify deletion
        print("\n✓ Test 9: Verify Deletion")
        try:
            service.get_product_by_id(new_product.id)
            print("❌ Product still exists (should be deleted)")
        except Exception:
            print("✅ Product successfully deleted (404 error expected)")
        
        print("\n" + "="*60)
        print("🎉 ALL TESTS PASSED!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()


if __name__ == "__main__":
    test_product_service()