"""Đọc các file CSV đầu vào của Olist thành DataFrame đã ép kiểu.

Module này chỉ ĐỌC và CHUẨN HÓA kiểu dữ liệu. Không join, không dedupe, không lọc
đơn hàng. Những việc đó làm ở lớp analytics (views), để mỗi bước có một trách nhiệm.

Cách dùng:
    from scripts.data_io import read_table, read_all
    orders = read_table("orders")

Chạy trực tiếp để kiểm tra toàn bộ đầu vào:
    .venv/bin/python -m scripts.data_io
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# Tên logic -> danh sách file (một bảng có thể nằm trong nhiều file)
SOURCES: dict[str, list[str]] = {
    "orders": ["olist_orders_dataset.csv"],
    "customers": ["olist_customers_dataset.csv"],
    "order_items": ["olist_order_items_dataset.csv"],
    "order_payments": ["olist_order_payments_dataset.csv"],
    "order_reviews": ["olist_order_reviews_dataset.csv"],
    "products": ["olist_products_dataset.csv"],
    "sellers": ["olist_sellers_dataset.csv"],
    "geolocation": ["olist_geolocation_dataset.csv"],
    "category_translation": ["product_category_name_translation.csv"],
}

# Số dòng kỳ vọng sau khi đọc (lấy từ lần profile dữ liệu gốc)
EXPECTED_ROWS: dict[str, int] = {
    "orders": 99_441,
    "customers": 99_441,
    "order_items": 112_650,
    "order_payments": 103_886,
    "order_reviews": 99_224,
    "products": 32_951,
    "sellers": 3_095,
    "geolocation": 1_000_163,
    "category_translation": 71,
}

# Cột thời gian: chuyển sang datetime, giá trị rỗng thành NaT
DATETIME_COLUMNS = {
    "orders": [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
}

# Cột số: chuyển sang float/int
NUMERIC_COLUMNS = {
    "order_items": {"price": float, "freight_value": float},
    "order_payments": {
        "payment_sequential": "Int64",
        "payment_installments": "Int64",
        "payment_value": float,
    },
    "order_reviews": {"review_score": "Int64"},
    "products": {
        "product_name_lenght": "Int64",
        "product_description_lenght": "Int64",
        "product_photos_qty": "Int64",
        "product_weight_g": "Int64",
        "product_length_cm": "Int64",
        "product_height_cm": "Int64",
        "product_width_cm": "Int64",
    },
}


def _read_csv(name: str) -> pd.DataFrame:
    """Đọc một bảng từ file CSV. Mọi cột đọc dạng chuỗi trước để giữ nguyên giá trị gốc."""
    (filename,) = SOURCES[name]
    path = RAW_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Thiếu file đầu vào: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=True)


def read_table(name: str) -> pd.DataFrame:
    """Đọc một bảng đầu vào đã ép kiểu.

    Ném lỗi nếu số dòng không khớp kỳ vọng, để phát hiện sớm file bị thiếu hoặc bị cắt.
    """
    if name not in SOURCES:
        raise KeyError(f"Bảng không tồn tại: {name}. Các bảng hợp lệ: {list(SOURCES)}")

    df = _read_csv(name)

    if len(df) != EXPECTED_ROWS[name]:
        raise ValueError(
            f"{name}: đọc được {len(df):,} dòng, kỳ vọng {EXPECTED_ROWS[name]:,} dòng"
        )

    for col in DATETIME_COLUMNS.get(name, []):
        df[col] = pd.to_datetime(df[col], errors="raise")

    for col, dtype in NUMERIC_COLUMNS.get(name, {}).items():
        if dtype is float:
            df[col] = pd.to_numeric(df[col], errors="raise").astype(float)
        else:
            df[col] = pd.to_numeric(df[col], errors="raise").astype(dtype)

    return df


def read_all() -> dict[str, pd.DataFrame]:
    """Đọc toàn bộ các bảng đầu vào."""
    return {name: read_table(name) for name in SOURCES}


if __name__ == "__main__":
    for name, df in read_all().items():
        print(f"{name:22s} {len(df):>10,d} dòng  {len(df.columns):>2d} cột")
    print("Đọc toàn bộ đầu vào thành công.")