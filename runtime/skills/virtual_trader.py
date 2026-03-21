"""
virtual-trader skill — daily virtual paper trading for SPX500 and Gold.
Uses real yfinance price data. No broker account, no KYC required.
Writes to agent-network/state/virtual_account.json — consumed by trading-report.
"""

import logging

from runtime.tools.virtual_account import run_virtual_account
from runtime.tools.trading import load_cycle_state

log = logging.getLogger(__name__)


def run() -> dict:
    """
    Returns result dict for the trading orchestrator:
    {
        "status": str,            # success | partial | failed
        "trades_made": int,
        "open_positions": int,
        "account_balance": float,
        "strategy_id": str,
        "summary": str,
        "escalate": bool,
        "escalation_reason": str,
        "errors": list[str],
    }
    """
    cycle_state = load_cycle_state()
    result      = run_virtual_account(cycle_state=cycle_state)

    escalate          = False
    escalation_reason = ""

    if result["status"] == "failed":
        escalate          = True
        escalation_reason = "Virtual trader failed: " + "; ".join(result.get("errors", []))

    return {
        **result,
        "escalate":          escalate,
        "escalation_reason": escalation_reason,
    }
