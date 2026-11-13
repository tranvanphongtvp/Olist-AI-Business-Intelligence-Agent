"""Lắp các node thành đồ thị LangGraph."""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agent import nodes
from agent.state import AgentState


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    builder = StateGraph(AgentState)

    builder.add_node("load_schema", nodes.load_schema)
    builder.add_node("plan_sql", nodes.plan_sql)
    builder.add_node("execute_sql", nodes.execute_sql)
    builder.add_node("analyze", nodes.analyze)
    builder.add_node("verify", nodes.verify_findings)
    builder.add_node("human_review", nodes.human_review)
    builder.add_node("report", nodes.report)

    builder.add_edge(START, "load_schema")
    builder.add_edge("load_schema", "plan_sql")
    builder.add_edge("plan_sql", "execute_sql")
    builder.add_conditional_edges(
        "execute_sql", nodes.route_after_execute, ["plan_sql", "analyze"]
    )
    builder.add_edge("analyze", "verify")
    builder.add_conditional_edges(
        "verify", nodes.route_after_verify, ["analyze", "human_review"]
    )
    builder.add_conditional_edges(
        "human_review", nodes.route_after_review, ["report", END]
    )
    builder.add_edge("report", END)

    # Checkpointer là bắt buộc để human_review có thể tạm dừng và tiếp tục sau đó
    return builder.compile(checkpointer=checkpointer or MemorySaver())
