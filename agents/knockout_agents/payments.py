"""Payment Protocol, seller side: the summary is free, the full report costs a fixed FET amount per drug.

The orchestrator sends RequestPayment; ASI:One's wallet answers CommitPayment with a transaction hash. The hash is
checked on the Fetch.ai ledger (recipient, amount, success) before the report is released, and each hash is
accepted once.
"""

import asyncio
from dataclasses import dataclass
from decimal import Decimal

import httpx

from knockout_agents import settings

VERIFY_ATTEMPTS = 5
VERIFY_DELAY_SECONDS = 2.0


@dataclass
class Verification:
    paid: bool
    reason: str


def _atomic(amount_fet: str) -> int:
    return int(Decimal(amount_fet) * Decimal(10) ** 18)


def _transfers(body: dict) -> list[tuple[str | None, str | None, list[dict]]]:
    transfers = []
    for message in ((body.get("tx") or {}).get("body") or {}).get("messages") or []:
        if "MsgSend" in (message.get("@type") or ""):
            transfers.append((message.get("from_address"), message.get("to_address"), message.get("amount") or []))
    return transfers


def check_transaction(body: dict, *, recipient: str, amount_fet: str, sender: str | None) -> Verification:
    """Pure check of a Cosmos REST transaction body against what the invoice asked for."""
    response = body.get("tx_response") or {}
    if int(response.get("code") or 0) != 0:
        return Verification(False, f"the transaction failed on chain (code {response.get('code')})")
    needed = _atomic(amount_fet)
    denomination = settings.fet_denomination()
    for from_address, to_address, coins in _transfers(body):
        if to_address != recipient:
            continue
        if sender and from_address != sender:
            continue
        paid = sum(int(coin.get("amount") or 0) for coin in coins if coin.get("denom") == denomination)
        if paid >= needed:
            return Verification(True, "verified on chain")
        return Verification(False, f"the transfer was {paid} {denomination}, {needed} needed")
    return Verification(False, "no transfer to this agent's wallet in that transaction")


async def verify_payment(transaction_id: str, *, recipient: str, amount_fet: str, sender: str | None) -> Verification:
    url = f"{settings.fet_rest_url()}/cosmos/tx/v1beta1/txs/{transaction_id}"
    last_problem = "the ledger has not indexed the transaction yet"
    async with httpx.AsyncClient(timeout=20.0) as client:
        for attempt in range(VERIFY_ATTEMPTS):
            try:
                response = await client.get(url)
            except httpx.HTTPError as error:
                last_problem = f"the ledger is unreachable ({error.__class__.__name__})"
            else:
                if response.status_code == 200:
                    return check_transaction(response.json(), recipient=recipient, amount_fet=amount_fet, sender=sender)
                last_problem = f"the ledger returned HTTP {response.status_code}"
            if attempt < VERIFY_ATTEMPTS - 1:
                await asyncio.sleep(VERIFY_DELAY_SECONDS)
    return Verification(False, last_problem)
