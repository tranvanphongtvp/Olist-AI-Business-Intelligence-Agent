#!/bin/bash
# Tạo lịch sử báo cáo và tài khoản GHI dành riêng cho API.
#
# Phân quyền:
#   - agent_ro: chỉ đọc analytics (agent dùng để truy vấn dữ liệu).
#   - reporter: ghi vào reports.runs và checkpoints (API dùng để lưu trạng thái và lịch sử).
#   Hai tài khoản tách biệt để agent không bao giờ có quyền ghi.
set -euo pipefail

: "${WRITER_DB_USER:?WRITER_DB_USER chưa được đặt trong .env}"
: "${WRITER_DB_PASSWORD:?WRITER_DB_PASSWORD chưa được đặt trong .env}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v writer_user="$WRITER_DB_USER" -v writer_pass="$WRITER_DB_PASSWORD" \
  -v db_name="$POSTGRES_DB" <<'EOSQL'
CREATE SCHEMA IF NOT EXISTS reports;
CREATE SCHEMA IF NOT EXISTS checkpoints;

CREATE TABLE reports.runs (
    run_id      UUID PRIMARY KEY,
    question    TEXT NOT NULL,
    status      TEXT NOT NULL
                CHECK (status IN ('running', 'awaiting_review', 'approved', 'rejected', 'failed')),
    findings    TEXT,
    warnings    TEXT[] NOT NULL DEFAULT '{}',
    report      TEXT,
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE ROLE :"writer_user" LOGIN PASSWORD :'writer_pass' NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE :"db_name" TO :"writer_user";
GRANT USAGE ON SCHEMA reports TO :"writer_user";
GRANT SELECT, INSERT, UPDATE ON reports.runs TO :"writer_user";

-- Checkpointer của LangGraph tự tạo bảng trong schema checkpoints khi khởi động
ALTER SCHEMA checkpoints OWNER TO :"writer_user";

-- Mặc định, mọi kết nối của tài khoản này dùng schema checkpoints để tạo bảng checkpoint
ALTER ROLE :"writer_user" SET search_path = checkpoints, reports;
ALTER ROLE :"writer_user" SET statement_timeout = '30s';
EOSQL
