import csv
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.product import Product


def import_tariffs(csv_path="data/tariff_rates.csv"):
    db: Session = SessionLocal()

    with open(csv_path, newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            product_name = row["product_name"]
            hts_code = row["hts_code"]
            tariff_rate = float(row["tariff_rate"])

            product = db.query(Product).filter(Product.name == product_name).first()

            if product:
                product.hts_code = hts_code
                product.tariff_rate = tariff_rate
                print(f"Updated {product_name}")

    db.commit()
    db.close()


if __name__ == "__main__":
    import_tariffs()