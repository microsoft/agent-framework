import asyncio
import httpx
from agent_framework import A2AAgent
from a2a.types import AgentCard
from a2a.client import A2ACardResolver

from a2a.utils.constants import EXTENDED_AGENT_CARD_PATH

# The server-side code can be implemented by following the guides found here
# https://a2a-protocol.org/latest/tutorials/python/4-agent-executor/ and
# https://a2a-protocol.org/latest/tutorials/python/5-start-server/

async def get_agent_card(
    *,
    base_url: str = "http://localhost:9999",
    token: str | None = None,
    timeout: float = 5.0
) -> AgentCard:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resolver = A2ACardResolver(httpx_client=client, base_url=base_url)

        public_card = await resolver.get_agent_card()

        if not public_card.supports_authenticated_extended_card or not token:
            return public_card

        try:
            extended_card = await resolver.get_agent_card(
                relative_card_path=EXTENDED_AGENT_CARD_PATH,
                http_kwargs={"headers": {"Authorization": f"Bearer {token}"}},
            )
            return extended_card
        except httpx.HTTPError:
            # Graceful fallback if auth is invalid or the endpoint errors out
            return public_card

async def main():
    stream = False
    agent = A2AAgent(name="HelloAgent", agent_card=await get_agent_card())
    if stream:
        stream = agent.run_streaming("Hello server")
        async for resp in stream:
            print("response: ", resp)
    else:
        response = await agent.run("Hello server")
        print("response: ", response)
        

if __name__ == "__main__":
    asyncio.run(main())
