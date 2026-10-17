"""Asks the orchestrator one question locally, as ASI:One would, and prints the reply and its card.

    python -m knockout_agents.ask "Is eculizumab expected to cause infections?"

Runs all five agents in this process against KNOCKOUT_API_URL, with nothing registered on Agentverse.
"""

import argparse
import asyncio
import json
import logging

from uagents_core.contrib.protocols.chat import ChatMessage, MetadataContent, TextContent
from uagents_core.contrib.protocols.payment import RequestPayment

from knockout_agents.local_chat import LocalChat


def print_message(message) -> None:
    if isinstance(message, RequestPayment):
        funds = ", ".join(f"{fund.amount} {fund.currency} ({fund.payment_method})" for fund in message.accepted_funds)
        print(f"\n[RequestPayment] {funds} to {message.recipient}: {message.description}")
        return
    for item in message.content:
        if isinstance(item, TextContent):
            print(item.text)
        elif isinstance(item, MetadataContent) and "card_payload" in item.metadata:
            payload = json.loads(item.metadata["card_payload"])
            print(f"\n[Interactive Card: {item.metadata.get('card_kind')}]")
            print(json.dumps(payload, indent=2, ensure_ascii=False))


async def run(question: str, wait_seconds: float) -> None:
    chat = LocalChat(allow_test_seeds=True)
    await chat.start()
    try:
        await chat.say(question, start_session=True)
        print_message(await chat.next((ChatMessage, RequestPayment), timeout=wait_seconds))
        while True:
            try:
                print_message(await chat.next((ChatMessage, RequestPayment), timeout=2))
            except TimeoutError:
                break
    finally:
        await chat.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the Knockout orchestrator one question locally")
    parser.add_argument("question")
    parser.add_argument("--wait", type=float, default=600.0, help="seconds to wait for the answer")
    parser.add_argument("--quiet", action="store_true", help="hide agent logs")
    arguments = parser.parse_args()
    if arguments.quiet:
        logging.disable(logging.WARNING)
    asyncio.run(run(arguments.question, arguments.wait))


if __name__ == "__main__":
    main()
