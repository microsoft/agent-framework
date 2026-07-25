# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable

import pytest
from aiohttp import web
from microsoft_agents.activity import Activity
from microsoft_agents.copilotstudio.client import ConnectionSettings, CopilotClient
from agent_framework_copilotstudio import CopilotStudioAgent


async def mock_server_handler(request: web.Request) -> web.StreamResponse:
    headers = {"Content-Type": "text/event-stream"}
    response = web.StreamResponse(headers=headers)
    await response.prepare(request)

    # 600KB line (larger than aiohttp default limit of 524288 bytes)
    long_data = "x" * 600000

    # Write event type line
    await response.write(b"event: activity\n")
    # Write data line
    data_line = f'data: {{"type":"message","text":"{long_data}","conversation":{{"id":"test"}}}}\n'.encode("utf-8")
    await response.write(data_line)
    return response


@pytest.fixture
async def local_server() -> AsyncIterable[str]:
    app = web.Application()
    app.router.add_post("/test", mock_server_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    address = runner.addresses[0]
    port = address[1]
    # Yield the URL to the test
    yield f"http://127.0.0.1:{port}/test"

    await site.stop()
    await runner.cleanup()


@pytest.mark.asyncio
async def test_copilot_client_post_request_long_line(local_server: str) -> None:
    settings = ConnectionSettings(
        environment_id="env",
        agent_identifier="agent",
        cloud=None,
        copilot_agent_type=None,
        custom_power_platform_cloud=None,
    )
    client = CopilotClient(settings=settings, token="token")

    activities: list[Activity] = []
    async for activity in client.post_request(local_server, {}, {}):
        activities.append(activity)

    assert len(activities) == 1
    assert activities[0].text == "x" * 600000
