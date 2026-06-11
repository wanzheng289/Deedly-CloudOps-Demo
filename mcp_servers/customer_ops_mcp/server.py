from __future__ import annotations

from typing import Any

from mcp_servers.common import ToolRegistry, WORKSPACE_ROOT, read_jsonl, write_jsonl

try:
    from project.backend.tools.customer_ops_tools import (
        _create_followup_task_impl,
        _get_customer_profile_impl,
        _search_customer_tickets_impl,
    )
except ModuleNotFoundError:
    from backend.tools.customer_ops_tools import (
        _create_followup_task_impl,
        _get_customer_profile_impl,
        _search_customer_tickets_impl,
    )


registry = ToolRegistry("customer_ops_mcp")
TICKETS_PATH = WORKSPACE_ROOT / "data" / "processed" / "customer_support" / "support_tickets.jsonl"


@registry.tool(description="Get customer profile and remembered facts.")
def get_customer_profile(customer_id: str) -> dict[str, Any]:
    import json

    return json.loads(_get_customer_profile_impl(customer_id))


@registry.tool(description="Search customer support tickets.")
def search_customer_tickets(customer_id: str, query: str = "", limit: int = 5) -> dict[str, Any]:
    import json

    return json.loads(_search_customer_tickets_impl(customer_id, query=query, limit=limit))


@registry.tool(description="Create a follow-up task for a customer.")
def create_followup_task(customer_id: str, summary: str) -> dict[str, Any]:
    import json

    return json.loads(_create_followup_task_impl(customer_id, summary))


@registry.tool(description="Update support ticket status in the processed JSONL store.")
def update_ticket_status(ticket_id: str, status: str) -> dict[str, Any]:
    rows = read_jsonl(TICKETS_PATH)
    updated = None
    for row in rows:
        if row.get("ticket_id") == ticket_id:
            row["status"] = status
            updated = row
            break
    if updated is None:
        return {"ok": False, "ticket_id": ticket_id, "error": "ticket_not_found"}
    write_jsonl(TICKETS_PATH, rows)
    return {"ok": True, "ticket": updated}


if __name__ == "__main__":
    registry.cli()
