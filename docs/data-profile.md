# Kết quả kiểm tra dữ liệu Olist

Kiểm tra trên file CSV thật, không dựa vào mô tả công khai.

## 1. Số dòng và khóa ngoại

Tất cả số dòng khớp với nguồn công khai. Mọi khóa ngoại đều khớp 100%:
`order_items` → `orders`, `products`, `sellers`; `payments`, `reviews` → `orders`; `orders` → `customers`.
Không có dòng trùng lặp hoàn toàn ở bảng nào, trừ `geolocation` (xem mục 4).

## 2. Các điểm dữ liệu cần xử lý

| Vấn đề | Số lượng | Hướng xử lý đề xuất |
|---|---|---|
| Đơn không có dòng sản phẩm | 775 | Doanh thu tính từ `order_items`, nên các đơn này tự động bằng 0 |
| Đơn không có thanh toán | 1 | Không ảnh hưởng đáng kể |
| Đơn không có đánh giá | 768 | Điểm trung bình chỉ tính trên đơn có đánh giá |
| Đơn có nhiều đánh giá | 547 | Gom về một dòng/đơn trước khi join |
| Đơn có nhiều dòng thanh toán | 2.961 | Gom `SUM(payment_value)` theo đơn trước khi join |
| Đơn có tổng thanh toán ≠ tổng sản phẩm + phí ship | 378 | Không dùng `payment_value` làm doanh thu gốc |
| Sản phẩm thiếu danh mục | 610 | Gán nhóm `unknown` |
| Danh mục không có trong bảng dịch | 2 (`pc_gamer`, `portateis_cozinha_e_preparadores_de_alimentos`) | Bổ sung bản dịch thủ công |
| Khách có nhiều `customer_id` | 99.441 `customer_id` / 96.096 `customer_unique_id` | Đếm khách bằng `customer_unique_id` |

## 3. Quyết định nghiệp vụ cần xác nhận

Doanh thu nên định nghĩa là **tổng `price`** (chưa gồm phí ship), còn `payment_value` chỉ dùng để đối soát.
Mặc định lọc đơn có trạng thái `delivered`, vì đơn đã hủy không tính là doanh thu.

Đây là quyết định nghiệp vụ, cần bạn xác nhận trước khi viết view `analytics`.

## 4. Dữ liệu geolocation

- File được chia làm 2 phần, ghép lại đúng **1.000.163 dòng**.
- **261.831 dòng trùng hoàn toàn** → còn khoảng 738 nghìn dòng duy nhất.
- Có **19.015 mã bưu chính** (3 chữ số đầu).
- Một mã bưu chính có tới 1.146 dòng, và thường có nhiều tọa độ khác nhau (trung vị 22 cặp tọa độ/mã).
- **8.559 mã** có tên thành phố hoặc bang khác nhau giữa các dòng (có thể do viết hoa, dấu tiếng Bồ Đào Nha).

**Nguyên nhân độ phủ thấp: mất số 0 đầu mã bưu chính ở file `part1`.**
- `part1`: 245.733 dòng có mã 4 chữ số (mất số 0 đầu). `part2`, `customers`, `sellers`: toàn bộ 5 chữ số.
- Trước khi sửa, 75,6% mã của khách và 66,7% mã của người bán khớp với geolocation.

**Cách xử lý:** đệm số 0 về đủ 5 chữ số (`LPAD(zip, 5, '0')`) ở lớp `analytics`, giữ nguyên `raw` đúng như file gốc.

Hướng đề xuất sau đó: tạo một dòng duy nhất cho mỗi mã bưu chính, lấy tọa độ trung bình và tên thành phố phổ biến nhất.

## 5. Phạm vi thời gian

Đơn hàng từ 2016-09-04 đến 2018-10-17.
