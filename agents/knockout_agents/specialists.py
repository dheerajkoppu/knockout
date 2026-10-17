"""The four specialists. Each asks the Knockout API for its slice and answers unknown, with the reason, on failure."""

import json
from collections.abc import Awaitable, Callable

from uagents import Agent, Context

from knockout_agents import knockout_api, slices
from knockout_agents.models import STATUS_UNKNOWN, SliceRequest, SliceResponse, slice_protocol
from knockout_agents.settings import AgentSpec

SliceBuilder = Callable[[SliceRequest], Awaitable[slices.Slice]]


async def build_target_slice(request: SliceRequest) -> slices.Slice:
    return slices.target_slice(await knockout_api.report(request.drug, refresh=request.refresh))


async def build_genetics_slice(request: SliceRequest) -> slices.Slice:
    return slices.genetics_slice(await knockout_api.report(request.drug))


async def build_label_slice(request: SliceRequest) -> slices.Slice:
    return slices.label_slice(await knockout_api.report(request.drug))


async def build_signal_slice(request: SliceRequest) -> slices.Slice:
    report = await knockout_api.report(request.drug)
    monitoring_problems = []
    trend = alerts = None
    try:
        trend = await knockout_api.trend(request.drug)
    except knockout_api.ApiError as error:
        monitoring_problems.append(f"trend unavailable: {error}")
    try:
        alerts = await knockout_api.alerts(request.drug)
    except knockout_api.ApiError as error:
        monitoring_problems.append(f"alerts unavailable: {error}")
    return slices.signal_slice(report, trend, alerts, monitoring_problems)


SLICE_BUILDERS: dict[str, SliceBuilder] = {
    "target": build_target_slice,
    "genetics": build_genetics_slice,
    "label": build_label_slice,
    "signal": build_signal_slice,
}


async def answer(spec: AgentSpec, builder: SliceBuilder, request: SliceRequest) -> SliceResponse:
    try:
        result = await builder(request)
    except knockout_api.ApiError as error:
        result = slices.Slice(STATUS_UNKNOWN, str(error))
    except Exception as error:  # a specialist must always answer, whatever broke
        result = slices.Slice(STATUS_UNKNOWN, f"{spec.name} failed: {error.__class__.__name__}: {error}")
    return SliceResponse(
        request_id=request.request_id,
        agent=spec.name,
        drug=request.drug,
        status=result.status,
        reason=result.reason,
        data_json=json.dumps(result.data),
    )


def attach_specialist(agent: Agent, spec: AgentSpec) -> None:
    builder = SLICE_BUILDERS[spec.key]
    protocol = slice_protocol()

    @protocol.on_message(SliceRequest, replies=SliceResponse)
    async def handle_slice_request(ctx: Context, sender: str, request: SliceRequest):
        ctx.logger.info(f"{spec.name}: slice for {request.drug!r} requested by {sender[:16]}")
        response = await answer(spec, builder, request)
        ctx.logger.info(f"{spec.name}: {response.status}{' (' + response.reason + ')' if response.reason else ''}")
        await ctx.send(sender, response)

    agent.include(protocol, publish_manifest=True)
