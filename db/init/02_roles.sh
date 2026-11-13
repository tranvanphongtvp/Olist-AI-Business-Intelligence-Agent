#!/bin/bash
# Tạo tài khoản chỉ đọc cho SQL Agent.
# Nguyên tắc: agent chỉ thấy schema analytics (các view đã làm sạch),
# KHÔNG thấy schema raw, và không có quyền ghi/sửa/xóa.
set -euo pipefail

: "${AGENT_DB_USER:?AGENT_DB_USER chưa được đặt trong .env}"
: "${AGENT_DB_PASSWORD:?AGENT_DB_PASSWORD chưa được đặt trong .env}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v agent_user="$AGENT_DB_USER" -v agent_pass="$AGENT_DB_PASSWORD" \
  -v db_name="$POSTGRES_DB" <<'EOSQL'
CREATE ROLE :"agent_user" LOGIN PASSWORD :'agent_pass' NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- Ép mọi transaction của agent là chỉ đọc, kể cả khi có lỗi trong code
ALTER ROLE :"agent_user" SET default_transaction_read_only = on;
-- Chặn truy vấn chạy quá lâu
ALTER ROLE :"agent_user" SET statement_timeout = '10s';

GRANT CONNECT ON DATABASE :"db_name" TO :"agent_user";
GRANT USAGE ON SCHEMA analytics TO :"agent_user";
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO :"agent_user";

-- Các view tạo sau này trong analytics cũng tự động được cấp quyền đọc
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO :"agent_user";
EOSQL
