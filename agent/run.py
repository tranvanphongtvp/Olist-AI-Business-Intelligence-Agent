"""Chạy agent từ dòng lệnh.

    .venv/bin/python -m agent.run "Doanh thu tháng này so với tháng trước có gì thay đổi?"

Agent sẽ dừng lại trước khi xuất báo cáo để bạn duyệt.
"""

from __future__ import annotations

import sys
import uuid

from langgraph.types import Command

from agent.graph import build_graph


def main() -> int:
    question = " ".join(sys.argv[1:]).strip() or input("Câu hỏi: ").strip()
    if not question:
        print("Chưa có câu hỏi.", file=sys.stderr)
        return 1

    graph = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    result = graph.invoke({"question": question}, config)

    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        print("\n=== PHÂN TÍCH ===")
        print(payload["findings"])
        if payload["warnings"]:
            print("\nCảnh báo, các số chưa khớp dữ liệu:", ", ".join(payload["warnings"]))
        decision = input(f"\n{payload['question']} > ").strip()
        result = graph.invoke(Command(resume=decision), config)

    if result.get("approved") and result.get("report"):
        print("\n=== BÁO CÁO ===")
        print(result["report"])
        return 0

    print("Báo cáo bị từ chối, không xuất.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
