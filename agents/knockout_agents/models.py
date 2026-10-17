"""Messages between the orchestrator and the four specialists."""

from uagents import Model, Protocol

SLICE_PROTOCOL_NAME = "KnockoutSliceProtocol"
SLICE_PROTOCOL_VERSION = "0.1.0"

STATUS_OK = "ok"
STATUS_UNKNOWN = "unknown"


class SliceRequest(Model):
    request_id: str
    drug: str
    refresh: bool = False


class SliceResponse(Model):
    request_id: str
    agent: str
    drug: str
    status: str
    reason: str | None = None
    # JSON text, so PRR values of Infinity survive the trip
    data_json: str = "{}"


def slice_protocol() -> Protocol:
    return Protocol(name=SLICE_PROTOCOL_NAME, version=SLICE_PROTOCOL_VERSION)
