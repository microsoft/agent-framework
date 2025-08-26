import asyncio
import httpx
from agent_framework import A2AAgent
from a2a.types import AgentCard
from a2a.client import A2ACardResolver

from a2a.utils.constants import EXTENDED_AGENT_CARD_PATH

# The server-side code can be implemented by following the guides found here
# https://a2a-protocol.org/latest/tutorials/python/4-agent-executor/ and
# https://a2a-protocol.org/latest/tutorials/python/5-start-server/

async def get_agent_card() -> AgentCard:
    base_url = 'http://localhost:9999'
    final_agent_card_to_use: AgentCard | None = None

    # Get an agent_card.
    async with httpx.AsyncClient() as httpx_client:
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=base_url,
            # agent_card_path uses default, extended_agent_card_path also uses default
        )

        _public_card = (
            await resolver.get_agent_card()
        )  # Fetches from default public path
        final_agent_card_to_use = _public_card

        if _public_card.supports_authenticated_extended_card:
            auth_headers_dict = {
                'Authorization': 'Bearer dummy-token-for-extended-card'
            }
            _extended_card = await resolver.get_agent_card(
                relative_card_path=EXTENDED_AGENT_CARD_PATH,
                http_kwargs={'headers': auth_headers_dict},
            )
            final_agent_card_to_use = (
                _extended_card  # Update to use the extended card
            )
    return final_agent_card_to_use

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
