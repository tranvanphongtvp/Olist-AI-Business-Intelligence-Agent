-- Lớp analytics: view đã ép kiểu, làm sạch và gom nhóm.
-- Đây là lớp DUY NHẤT tài khoản agent_ro được phép đọc.
--
-- Quy tắc nghiệp vụ đã chốt:
--   * Doanh thu = tổng price (không gồm phí ship).
--   * Chỉ tính đơn có order_status = 'delivered' cho doanh thu.
--   * Khách được đếm theo customer_unique_id, không theo customer_id.

-- Đơn hàng kèm khách thật (customer_unique_id). Giữ mọi trạng thái đơn.
CREATE OR REPLACE VIEW analytics.v_orders AS
SELECT
    o.order_id,
    c.customer_unique_id,
    o.order_status,
    o.order_purchase_timestamp::timestamp        AS purchased_at,
    o.order_delivered_customer_date::timestamp   AS delivered_at,
    o.order_estimated_delivery_date::timestamp   AS estimated_delivery_at
FROM raw.orders o
JOIN raw.customers c ON c.customer_id = o.customer_id;

-- Tổng thanh toán và số kỳ trả góp, một dòng cho mỗi đơn.
-- Gom ở đây để tránh nhân đôi doanh thu khi join (một đơn có thể có nhiều dòng thanh toán).
CREATE OR REPLACE VIEW analytics.v_order_payments AS
SELECT
    order_id,
    SUM(payment_value::numeric)        AS payment_total,
    MAX(payment_installments::int)     AS max_installments
FROM raw.order_payments
GROUP BY order_id;

-- Điểm đánh giá trung bình, một dòng cho mỗi đơn.
-- Gom ở đây để tránh nhân đôi đơn khi join (một đơn có thể có nhiều đánh giá).
CREATE OR REPLACE VIEW analytics.v_order_reviews AS
SELECT
    order_id,
    AVG(review_score::numeric)  AS avg_review_score,
    COUNT(*)                    AS review_count
FROM raw.order_reviews
GROUP BY order_id;

-- Sản phẩm kèm tên danh mục tiếng Anh.
-- Thiếu danh mục -> 'unknown'. Danh mục không có trong bảng dịch -> giữ tên gốc tiếng Bồ.
CREATE OR REPLACE VIEW analytics.v_products AS
SELECT
    p.product_id,
    COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category_en
FROM raw.products p
LEFT JOIN raw.category_translation t
       ON t.product_category_name = p.product_category_name;

-- Từng món hàng trong đơn đã giao. Đây là nguồn chính để tính doanh thu.
CREATE OR REPLACE VIEW analytics.v_order_items_delivered AS
SELECT
    oi.order_id,
    oi.order_item_id::int                                 AS order_item_id,
    oi.product_id,
    p.category_en,
    oi.seller_id,
    o.purchased_at,
    date_trunc('month', o.purchased_at)::date             AS sales_month,
    oi.price::numeric                                     AS price,
    oi.freight_value::numeric                             AS freight_value
FROM raw.order_items oi
JOIN analytics.v_orders o   ON o.order_id = oi.order_id
JOIN analytics.v_products p ON p.product_id = oi.product_id
WHERE o.order_status = 'delivered';

-- Doanh thu và số lượng bán theo sản phẩm theo tháng.
-- Dùng cho câu hỏi kiểu "sản phẩm nào giảm doanh thu mạnh so với tháng trước".
CREATE OR REPLACE VIEW analytics.v_product_monthly_sales AS
SELECT
    product_id,
    category_en,
    sales_month,
    SUM(price)  AS revenue,
    COUNT(*)    AS units_sold
FROM analytics.v_order_items_delivered
GROUP BY product_id, category_en, sales_month;

-- Thống kê theo khách thật. Chỉ đếm đơn đã giao.
CREATE OR REPLACE VIEW analytics.v_customers AS
SELECT
    customer_unique_id,
    COUNT(*) FILTER (WHERE order_status = 'delivered')  AS delivered_order_count,
    MIN(purchased_at)                                    AS first_purchase_at,
    MAX(purchased_at)                                    AS last_purchase_at
FROM analytics.v_orders
GROUP BY customer_unique_id;