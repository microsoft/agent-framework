#!/usr/bin/env python3
"""Simple integration test for AWS Bedrock client."""
import asyncio
import os

from agent_framework_bedrock import BedrockClient


async def test_basic_chat():
    """Test basic chat completion with Bedrock."""
    print("🔧 Initializing BedrockClient...")

    # When using bearer tokens (API keys), use cross-region inference profile ARNs
    client = BedrockClient(
        bearer_token=os.getenv("AWS_BEARER_TOKEN_BEDROCK"),
        region_name=os.getenv("AWS_REGION_NAME", "us-east-1"),
        model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    )

    print("✅ Client initialized")
    print(f"📍 Region: {client.region_name}")
    print(f"🤖 Model: {client.model_id}")
    print(f"🔄 Using Converse API: {client.use_converse_api}")

    print("\n📤 Sending test message: 'Hello! Can you respond with just the word SUCCESS?'")

    try:
        response = await client.get_response("Hello! Can you respond with just the word SUCCESS?")

        print("\n✅ Response received!")
        print(f"📝 Response ID: {response.response_id}")
        print(f"🤖 Model: {response.model_id}")
        print(f"💬 Message: {response.messages[0].text}")
        print(f"📊 Usage: {response.usage_details.input_token_count} input, {response.usage_details.output_token_count} output, {response.usage_details.total_token_count} total tokens")
        print(f"🏁 Finish Reason: {response.finish_reason}")

        return True

    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_streaming_chat():
    """Test streaming chat completion with Bedrock."""
    print("\n" + "="*60)
    print("🔧 Testing streaming response...")

    # When using bearer tokens (API keys), use cross-region inference profile ARNs
    client = BedrockClient(
        bearer_token=os.getenv("AWS_BEARER_TOKEN_BEDROCK"),
        region_name=os.getenv("AWS_REGION_NAME", "us-east-1"),
        model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    )

    print("📤 Sending streaming request: 'Count to 5'")
    print("📥 Streaming response: ", end="", flush=True)

    try:
        async for chunk in client.get_streaming_response("Count to 5 slowly"):
            for content in chunk.contents:
                if hasattr(content, 'text') and content.text:
                    print(content.text, end="", flush=True)

        print("\n✅ Streaming test completed!")
        return True

    except Exception as e:
        print(f"\n❌ Streaming error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run integration tests."""
    print("="*60)
    print("🚀 AWS Bedrock Integration Tests")
    print("="*60)

    # Check environment
    if not os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
        print("❌ AWS_BEARER_TOKEN_BEDROCK not set!")
        return

    print(f"✅ Bearer token: {os.getenv('AWS_BEARER_TOKEN_BEDROCK')[:20]}...")
    print(f"✅ Region: {os.getenv('AWS_REGION_NAME', 'us-east-1')}")

    print("\n" + "="*60)

    # Test 1: Basic chat
    success1 = await test_basic_chat()

    # Test 2: Streaming
    success2 = await test_streaming_chat()

    print("\n" + "="*60)
    print("📊 Test Results:")
    print(f"  {'✅' if success1 else '❌'} Basic chat completion")
    print(f"  {'✅' if success2 else '❌'} Streaming chat completion")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
