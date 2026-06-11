from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.tools.customer_ops_tools import (
    _create_followup_task_impl,
    _get_customer_profile_impl,
    _search_customer_tickets_impl,
    _update_customer_memory_impl,
)


def _print_section(title: str, payload: str) -> None:
    print(f"\n## {title}")
    parsed = json.loads(payload)
    print(json.dumps(parsed, ensure_ascii=False, indent=2)[:3000])


def main() -> None:
    customer_id = "CustQRWQE"
    _print_section("Customer Profile", _get_customer_profile_impl(customer_id))
    _print_section("Historical Tickets", _search_customer_tickets_impl(customer_id, "SSO urgent access", limit=3))
    _print_section(
        "Update Customer Memory",
        _update_customer_memory_impl(
            customer_id,
            {
                "content": "Customer previously had an urgent SSO course access issue and prefers concise email updates.",
                "importance": 3,
                "tags": ["sso", "access", "communication_preference"],
            },
        ),
    )
    _print_section(
        "Create Follow-up",
        _create_followup_task_impl(customer_id, "Confirm whether SSO course access remains stable after the workaround."),
    )


if __name__ == "__main__":
    main()
