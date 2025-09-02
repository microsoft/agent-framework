import asyncio

from typing import Annotated

from agent_framework import ChatResponseUpdate, ChatMessage, FunctionResultContent, TextContent, ai_function
from agent_framework.openai import OpenAIResponsesClient

@ai_function
async def get_weather(location: Annotated[str, "The location as a city name"]) -> str:
    """Get the current weather in a given location."""
    # Implementation of the tool to get weather
    return f"The current weather in {location} is sunny."


@ai_function
async def get_location() -> str:
    """Get the current user's location."""
    # Implementation of the tool to get location
    return f"The current location is Seattle."

async def main():
    client = OpenAIResponsesClient(ai_model_id="gpt-4o")

    messages: list[ChatMessage] = [
        ChatMessage(role="user", text="What is the weather?")
    ]
    
    streaming = False

    if streaming:
        # NOTE: streaming with tools DOES NOT WORK!
        # Test that the client can be used to get a response
        response = client.get_streaming_response(
            messages=messages,
            background=True,
            store=True,
            tools=[get_weather, get_location],
        )

        print("Streamed responses:")
        # There is no final response with the full text like autogen.
        full_message: str = ""
        conversation_id: str | None = None
        sequence_number: int = 0
        async for message in response:
            assert message is not None
            assert isinstance(message, ChatResponseUpdate)
            if message.conversation_id:
                conversation_id = message.conversation_id or message.message_id
            if sequence_number > 10:
                break
            if message.sequence_number:
                sequence_number = message.sequence_number
            for chunk in message.contents:
                if isinstance(chunk, TextContent) and chunk.text:
                    full_message += chunk.text
                    # The chunk is a string.
                    print(chunk.text, flush=True, end="")

        print("\n\n------------\n")
        print("partial message:", full_message)
        print("\n\n------------\n")
        
        assert conversation_id is not None
        response = client.get_streaming_response(
            conversation_id=conversation_id,
            sequence_number=sequence_number,
            background=True,
            store=True,
            tools=[get_weather, get_location],
        )
        async for message in response:
            assert message is not None
            assert isinstance(message, ChatResponseUpdate)
            if message.conversation_id:
                conversation_id = message.conversation_id or message.message_id
            if message.sequence_number:
                sequence_number = message.sequence_number
            for chunk in message.contents:
                if isinstance(chunk, TextContent) and chunk.text:
                    full_message += chunk.text
                    # The chunk is a string.
                    print(chunk.text, flush=True, end="")

        print("\n\n------------\n")
        print("The complete response:", flush=True)
        print(full_message, flush=True)
    else:
        response = await client.get_response(
            messages=messages,
            background=True,
            store=True,
            tools=[get_weather, get_location],
        )

        while response.status and response.status.value != "completed":
            assert response.response_id is not None
            # background and store must be True for this to work properly.
            # Allowing other permutations will require some very careful code changes 
            response = await client.get_response(
                background=True,
                store=True,
                message_id=response.response_id,
                tools=[get_weather, get_location],
            )
            await asyncio.sleep(1)
        # print(response.model_dump(exclude={"raw_representation"}))
        assert response.status and response.status.value == "completed"
        print(response)

if __name__ == "__main__":
  asyncio.run(main())
