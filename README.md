# Olist AI Business Intelligence Agent

Agent LangGraph đọc dữ liệu bán hàng Olist, tự viết SQL, phân tích, kiểm chứng số liệu và gửi báo cáo
qua Telegram/n8n. Dữ liệu lấy từ
[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).

> **Lưu ý về phạm vi dữ liệu:** bộ dữ liệu chỉ có đơn từ **2016-09-04 đến 2018-10-17**.
> Câu hỏi kiểu "tháng này" sẽ không có dữ liệu — hãy hỏi theo tháng/năm cụ thể (ví dụ tháng 8/2018).

---

## 1. Kiến trúc

```
CSV gốc (Kaggle)
    │  scripts/load_raw.py  (COPY, một transaction, kiểm tra số dòng)
    ▼
schema raw        — lớp bronze: mọi cột TEXT, giữ nguyên dữ liệu gốc
    │  scripts/build_views.py + sql/views/*.sql
    ▼
schema analytics  — view đã ép kiểu, join, dedupe, gom nhóm
    │  chỉ tài khoản agent_ro được SELECT
    ▼
SQL Agent (LangGraph)
    load_schema → plan_sql → execute_sql → analyze → verify
                                    ▲                    │
                                    └─ sửa SQL nếu lỗi   ▼
                                              human_review (interrupt)
                                                    │
                                          ┌─────────┴─────────┐
                                       reject              approve
                                          ▼                   ▼
                                         END               report
    │
    ▼
FastAPI (api/)  ──►  n8n  ──►  Telegram
   lưu run_id, status, findings, warnings, report vào Postgres
```

- `raw` là kho nguyên liệu còn nguyên bao bì; `analytics` là quầy đã sơ chế.
- Agent **không** đọc được `raw`, **không** có quyền ghi. Tài khoản ghi lịch sử (`reporter`) tách riêng.
- LangGraph lưu checkpoint trong Postgres, nên một lần chạy có thể dừng chờ duyệt rất lâu
  (kể cả sau khi khởi động lại API) rồi mới duyệt tiếp.

### Các view trong `analytics`

| View | Nội dung |
|---|---|
| `v_orders` | Đơn hàng + `customer_unique_id`, giữ mọi trạng thái |
| `v_order_payments` | Tổng thanh toán, số kỳ trả góp — một dòng/đơn |
| `v_order_reviews` | Điểm đánh giá trung bình — một dòng/đơn |
| `v_products` | Sản phẩm + tên danh mục tiếng Anh (thiếu → `unknown`) |
| `v_order_items_delivered` | Từng món hàng của đơn **đã giao** — nguồn tính doanh thu |
| `v_product_monthly_sales` | Doanh thu, số lượng bán theo sản phẩm/tháng |
| `v_customers` | Thống kê theo khách thật (`customer_unique_id`) |

### Quy tắc nghiệp vụ đã chốt

- **Doanh thu** = `SUM(price)`, không gồm phí ship.
- Chỉ tính đơn có `order_status = 'delivered'`.
- **Khách** đếm theo `customer_unique_id` (96.096 khách thật / 99.441 `customer_id`).
- Không dùng `payment_value` làm doanh thu gốc (có 378 đơn lệch với tiền hàng + ship);
  `payment_value` chỉ để đối soát.

---

## 2. Yêu cầu môi trường

| Thành phần | Phiên bản / ghi chú |
|---|---|
| Python | 3.10+ (đã kiểm chứng với 3.10.11) |
| Docker Desktop | Có `docker compose` |
| Git Bash (Windows) | Khuyến nghị, để dùng `source .env` |
| LLM API key | OpenAI **hoặc** Groq (Groq dùng API tương thích OpenAI) |
| n8n + Telegram bot | Chỉ cần nếu muốn báo cáo/duyệt qua Telegram |

Trên Windows, dùng đúng đường dẫn `Scripts`:

```text
.venv/Scripts/python        ✅
.venv/bin/python            ❌ (Linux/macOS)
```

---

## 3. Cấu trúc thư mục

```text
.
├── docker-compose.yml          # PostgreSQL 16
├── requirements.txt
├── .env.example                # mẫu cấu hình, KHÔNG chứa khóa thật
├── db/init/                    # chạy 1 lần khi volume Postgres còn trống
│   ├── 01_schema.sql           # tạo schema raw/analytics + 9 bảng bronze
│   ├── 02_roles.sh             # tài khoản agent_ro (chỉ đọc analytics)
│   └── 03_reports.sh           # schema reports/checkpoints + tài khoản reporter
├── scripts/
│   ├── load_raw.py             # CSV → raw, kiểm tra số dòng
│   ├── build_views.py          # chạy sql/views/*.sql
│   └── data_io.py              # đọc/ép kiểu CSV, danh sách file + số dòng kỳ vọng
├── sql/views/001_analytics.sql # 7 view analytics
├── agent/                      # LangGraph: graph, nodes, SQL guard, verify, LLM config
├── api/                        # FastAPI cho n8n gọi
├── n8n/
│   ├── olist_daily_report.json      # workflow 1: báo cáo 7h + duyệt
│   └── olist_approval_callback.json # workflow 2: hỏi đáp + nhận nút duyệt
├── tests/                      # unit test + integration test (tự skip nếu thiếu DB)
├── docs/data-profile.md        # kết quả kiểm tra dữ liệu thật
└── data/raw/                   # CSV tải từ Kaggle (KHÔNG commit)
```

---

## 4. Cài đặt và chạy lần đầu

### 4.1. Clone và tạo môi trường

```bash
git clone https://github.com/<ten-tai-khoan>/<ten-repo>.git
cd <ten-repo>

python -m venv .venv

# Git Bash / Linux / macOS
.venv/Scripts/python -m pip install --upgrade pip      # Windows
.venv/Scripts/python -m pip install -r requirements.txt
```

> Linux/macOS thay `.venv/Scripts/python` bằng `.venv/bin/python`.

Nếu dùng PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4.2. Tạo file `.env`

```bash
cp .env.example .env
```

Điền các giá trị sau (xem giải thích trong `.env.example`):

| Biến | Bắt buộc | Ý nghĩa |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | ✅ | Tài khoản admin của Postgres trong Docker |
| `POSTGRES_DB` | ✅ | Tên database (mặc định `olist`) |
| `POSTGRES_PORT` | ✅ | Cổng Postgres trên máy, mặc định `5432` |
| `POSTGRES_HOST` | ➖ | Mặc định `localhost`, chỉ đổi khi DB ở máy khác |
| `AGENT_DB_USER` / `AGENT_DB_PASSWORD` | ✅ | Tài khoản **chỉ đọc** cho agent |
| `WRITER_DB_USER` / `WRITER_DB_PASSWORD` | ✅ | Tài khoản **ghi** lịch sử run + checkpoint |
| `LLM_PROVIDER` | ✅ | `openai` (mặc định) hoặc `groq` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | Nếu dùng OpenAI | |
| `GROQ_API_KEY` / `GROQ_MODEL` | Nếu dùng Groq | |
| `API_KEY` | ✅ | Chuỗi ngẫu nhiên dài; n8n gửi trong header `X-API-Key` |

Tạo `API_KEY` ngẫu nhiên:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

> **Không commit `.env`.** File này đã nằm trong `.gitignore`.

### 4.3. Khởi động PostgreSQL

```bash
docker compose up -d
docker compose ps          # đợi trạng thái healthy
```

Các script trong `db/init/` **chỉ chạy khi volume còn trống** (lần đầu). Nếu sửa file init
sau này, phải tạo lại volume — xem mục 9.

### 4.4. Tải dữ liệu Kaggle

Tải dataset **Brazilian E-Commerce Public Dataset by Olist** rồi đặt đúng 9 file CSV vào `data/raw/`:

```text
olist_customers_dataset.csv
olist_geolocation_dataset.csv
olist_order_items_dataset.csv
olist_order_payments_dataset.csv
olist_order_reviews_dataset.csv
olist_orders_dataset.csv
olist_products_dataset.csv
olist_sellers_dataset.csv
product_category_name_translation.csv
```

`data/raw/` không được commit vì quá lớn. `scripts/load_raw.py` sẽ báo lỗi nếu thiếu file.

### 4.5. Nạp dữ liệu và tạo view

**Git Bash / Linux / macOS:**

```bash
set -a; source .env; set +a
PYTHONIOENCODING=utf-8 .venv/Scripts/python -m scripts.load_raw
PYTHONIOENCODING=utf-8 .venv/Scripts/python -m scripts.build_views
```

**PowerShell:**

```powershell
$env:PYTHONIOENCODING = "utf-8"
Get-Content .env | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    Set-Item -Path "env:$($k.Trim())" -Value $v.Trim()
}
.\.venv\Scripts\python.exe -m scripts.load_raw
.\.venv\Scripts\python.exe -m scripts.build_views
```

Kết quả mong đợi: 9 bảng `raw.*` khớp đúng số dòng, sau đó là
`Tạo view analytics thành công.`

> `load_raw` chạy toàn bộ trong **một transaction**: chỉ cần một bảng lệch số dòng là rollback,
> DB giữ nguyên trạng thái cũ. Chạy lại nhiều lần vẫn cho kết quả giống nhau.

---

## 5. Chạy agent từ dòng lệnh

`agent/config.py` tự đọc `.env`, nên không cần `source .env` trước.

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python -m agent.run "Doanh thu tháng 8/2018 so với tháng 7/2018 thay đổi bao nhiêu?"
```

Agent sẽ:

1. Đọc schema `analytics` và viết SQL.
2. Chạy SQL bằng `agent_ro`, phân tích kết quả.
3. Kiểm chứng: con số nào không tìm thấy trong dữ liệu truy vấn sẽ thành **cảnh báo**.
4. Dừng lại và hỏi bạn `approve` hoặc `reject` (cần terminal tương tác).
5. Chỉ khi `approve` mới sinh báo cáo Markdown.

---

## 6. Chạy API cho n8n

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Mở http://localhost:8000/health để kiểm tra (không cần khóa).

| Method | Đường dẫn | Mục đích |
|---|---|---|
| `POST` | `/runs` | Bắt đầu phân tích, trả `status = awaiting_review` |
| `POST` | `/runs/{run_id}/decision` | `{"decision": "approve"}` hoặc `{"decision": "reject"}` |
| `GET` | `/runs/{run_id}` | Xem trạng thái, findings, warnings, report |
| `GET` | `/runs?limit=20` | Danh sách run gần đây |
| `GET` | `/health` | Kiểm tra API sống |

Mọi endpoint trừ `/health` yêu cầu header `X-API-Key`.

**Ví dụ:**

```bash
curl -s -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"question": "Doanh thu tháng 8/2018 so với tháng 7/2018 thay đổi bao nhiêu?"}'
```

Trả về:

```json
{
  "run_id": "…",
  "question": "…",
  "status": "awaiting_review",
  "findings": "…",
  "warnings": [],
  "report": null,
  "error": null,
  "created_at": "…"
}
```

Duyệt:

```bash
curl -s -X POST http://localhost:8000/runs/<run_id>/decision \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"decision": "approve"}'
```

- `404`: không tìm thấy run / sai định dạng `run_id`.
- `409`: run không ở trạng thái `awaiting_review` (ví dụ đã duyệt rồi).
- `401`: thiếu hoặc sai `X-API-Key`.
- `422`: câu hỏi ngoài khoảng 3–500 ký tự.

---

## 7. n8n + Telegram

Phần này chỉ cần khi muốn báo cáo tự động 7h sáng và duyệt/hỏi đáp qua Telegram.

### 7.1. Chạy n8n và tunnel HTTPS

Telegram **bắt buộc** webhook là HTTPS công khai. Cách đơn giản là chạy n8n + Cloudflare quick tunnel
trong cùng một compose project. Lưu đoạn dưới thành `compose.yaml` trong một thư mục riêng
(ví dụ `D:\n8n`), **không** dùng chung với `docker-compose.yml` của Postgres:

```yaml
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n
    container_name: n8n
    restart: unless-stopped
    ports:
      - "5678:5678"
    environment:
      - TZ=Asia/Ho_Chi_Minh
      - GENERIC_TIMEZONE=Asia/Ho_Chi_Minh
      - WEBHOOK_URL=https://<ten-tunnel>.trycloudflare.com/
      - N8N_PROXY_HOPS=1
    volumes:
      - ./data:/home/node/.n8n

  n8n-tunnel:
    image: cloudflare/cloudflared:latest
    container_name: n8n-tunnel
    restart: unless-stopped
    command: tunnel --no-autoupdate --protocol http2 --url http://n8n:5678
```

```bash
docker compose up -d
docker logs n8n-tunnel 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com'
```

Lấy URL vừa in ra, gán vào `WEBHOOK_URL` (có `/` ở cuối) rồi:

```bash
docker compose up -d          # recreate n8n với biến mới
```

Sau đó mở n8n tại http://localhost:5678 và tạo tài khoản owner. Việc import/publish workflow
làm ở mục 7.2.

> **Quick tunnel đổi URL mỗi lần container tunnel khởi động lại.** Khi đổi URL phải cập nhật
> `WEBHOOK_URL`, recreate n8n, rồi mở lại workflow để webhook đăng ký lại với Telegram.
> Muốn URL cố định thì dùng Cloudflare named tunnel + tên miền riêng.

### 7.2. Import 2 workflow

Trong n8n: **Import from file**.

| File | Vai trò |
|---|---|
| `n8n/olist_daily_report.json` | 7h sáng mỗi ngày: gọi API, tự duyệt nếu không có cảnh báo, gửi Telegram; có cảnh báo thì gửi nút Duyệt/Từ chối |
| `n8n/olist_approval_callback.json` | Nhận tin nhắn câu hỏi tự do và nhận callback nút Duyệt/Từ chối, gọi API rồi gửi kết quả |

Tạo 2 credential trong n8n:

1. **Header Auth** tên `Olist API key`
   - Name: `X-API-Key`
   - Value: đúng `API_KEY` trong `.env`
2. **Telegram API** với token lấy từ [@BotFather](https://t.me/BotFather).

Sau đó mở từng workflow, gán credential vào các node HTTP/Telegram và sửa các giá trị cấu hình:

| Workflow | Node | Giá trị cần sửa |
|---|---|---|
| 1 | `Cấu hình` | `api_base`, `question`, `manager_chat_id` |
| 2 | `Cấu hình Telegram` | `api_base`, `allowed_user_id` |

- `api_base`: n8n chạy trong Docker còn API chạy trên máy → giữ `http://host.docker.internal:8000`.
  Trên Linux cần thêm `extra_hosts: ["host.docker.internal:host-gateway"]` cho service n8n.
- `manager_chat_id`: chat ID nhận báo cáo (lấy bằng bot @userinfobot).
- `allowed_user_id`: **chỉ Telegram user id này** được hỏi và bấm duyệt.

Nhắn `/start` cho bot trước, nếu không bot không gửi được tin cho bạn.

### 7.3. Luồng hoạt động

**Báo cáo 7h (workflow 1):**

```text
Lịch 7h → Cấu hình → POST /runs
                         │
             warnings rỗng? ── có ──► Tự động duyệt → Gửi báo cáo Telegram
                         │
                        không
                         ▼
             Gửi yêu cầu duyệt (nút Duyệt / Từ chối)
```

**Khi bấm nút (workflow 2):**

```text
Telegram callback → kiểm tra allowed_user_id → POST /runs/{run_id}/decision
                                                        │
                                              approve ──► gửi báo cáo
                                              reject  ──► dừng
```

**Hỏi tự do (workflow 2):** nhắn một câu hỏi 3–500 ký tự → workflow gọi `POST /runs` →
nếu có cảnh báo thì gửi nút duyệt, nếu không thì tự duyệt và trả báo cáo ngay trong chat.

Lưu ý:

- Chỉ **một** workflow được dùng Telegram Trigger cho mỗi bot. Đừng tạo thêm trigger thứ ba.
- Workflow 2 phải được **publish** thì webhook mới hoạt động.
- Đừng bấm **Execute step** trên Telegram Trigger khi workflow đang publish — n8n báo
  *"can't listen for test executions at the same time as listening for production ones"*.
  Muốn thử: nhắn thật cho bot, rồi xem tab **Executions**.
- Tin nhắn Telegram giới hạn 4096 ký tự; workflow tự chia nhỏ ở 3500 ký tự.

---

## 8. Kiểm thử

```bash
set -a; source .env; set +a
PYTHONIOENCODING=utf-8 .venv/Scripts/python -m unittest discover -s tests -t . -v
```

- `test_sql_guard`, `test_verify`, `test_llm_config`, `test_graph_offline`: chạy offline, không cần LLM thật.
- `test_api`: cần Postgres đã nạp dữ liệu và tài khoản `reporter`; LLM được thay bằng bản giả.
  Nếu thiếu biến môi trường, test này tự **skip**.
- Test không gọi API thật, không tiêu token.

---

## 9. Xử lý sự cố

| Hiện tượng | Nguyên nhân / cách sửa |
|---|---|
| `bash: .venv/bin/python: No such file or directory` | Windows dùng `.venv/Scripts/python` |
| `ModuleNotFoundError: No module named 'psycopg'` | Đang chạy Python toàn cục. Dùng đúng `.venv/Scripts/python` hoặc activate venv |
| `Thiếu biến môi trường OPENAI_API_KEY` | Điền `OPENAI_API_KEY` + `OPENAI_MODEL`, hoặc đặt `LLM_PROVIDER=groq` và điền `GROQ_API_KEY` + `GROQ_MODEL`. Kiểm tra `.env` nằm ở thư mục gốc |
| Agent trả lời "không có dữ liệu" | Câu hỏi nằm ngoài 2016-09 → 2018-10 |
| `pg_isready ... no response` | Postgres còn đang khởi động: `docker compose logs postgres`, đợi `healthy` |
| `port is already allocated` (5432) | Đổi `POSTGRES_PORT=5433` trong `.env` rồi `docker compose up -d` |
| Sửa `db/init/*.sql` nhưng không có tác dụng | Init script chỉ chạy khi volume trống. `docker compose down -v` (**xóa toàn bộ DB**) rồi `up -d` và nạp lại |
| `UnicodeEncodeError` / tiếng Việt bị lỗi | Đặt `PYTHONIOENCODING=utf-8` |
| Telegram báo *"An HTTPS URL must be provided for webhook"* | Chưa có tunnel HTTPS hoặc workflow chưa publish |
| Cloudflare Error 1033 | Container tunnel không chạy: `docker compose ps`, `docker logs n8n-tunnel` |
| n8n không gọi được API | API phải chạy `--host 0.0.0.0`; trong Docker dùng `host.docker.internal:8000` |
| API trả `401` | `X-API-Key` trong credential không khớp `API_KEY` |
| API trả `409` khi duyệt | Run không còn ở `awaiting_review` (đã duyệt/từ chối trước đó) |
| n8n báo *"can't listen for test executions…"* | Workflow đang publish; không bấm Execute step, nhắn thật cho bot rồi xem **Executions** |
| Đổi tunnel URL nhưng Telegram không nhận tin | Cập nhật `WEBHOOK_URL`, recreate n8n, publish lại workflow |

---

## 10. Đưa lên GitHub

Repo chỉ nên chứa **code + cấu hình mẫu**, không chứa dữ liệu và bí mật:

- `.env` — chứa khóa API/mật khẩu, đã bị ignore.
- `data/raw/` — CSV Kaggle, tải lại theo hướng dẫn mục 4.4.
- `.venv/`, `__pycache__/` — môi trường và cache Python.
- `tools/` — binary cloudflared (nếu tải về), không commit.
- `*.bak` — bản sao lưu khi sửa workflow.

Người clone repo chỉ cần: tạo `.env` từ `.env.example` → `docker compose up -d` → tải CSV →
`load_raw` → `build_views` → chạy agent/API.

Nếu thư mục hiện tại chưa phải git repo:

```bash
git init
git add .
git status                # kiểm tra không có .env hay CSV trong danh sách
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<ten-tai-khoan>/<ten-repo>.git
git push -u origin main
```

---

## 11. Trạng thái

- [x] Schema bronze, phân quyền `agent_ro` / `reporter`
- [x] Nạp raw (khớp đủ số dòng) và 7 view `analytics`
- [x] LangGraph agent: plan → SQL → phân tích → kiểm chứng → duyệt → báo cáo
- [x] FastAPI lưu trạng thái trong Postgres, có `X-API-Key`
- [x] n8n: báo cáo 7h, duyệt qua Telegram (nút bấm), hỏi đáp tự do qua Telegram
- [x] Hỗ trợ OpenAI và Groq qua `LLM_PROVIDER`
- [ ] Kiểm thử live end-to-end với bot Telegram thật (cần bot token + chat id của bạn)#   O l i s t - A I - B u s i n e s s - I n t e l l i g e n c e - A g e n t  
 #   O l i s t - A I - B u s i n e s s - I n t e l l i g e n c e - A g e n t  
 