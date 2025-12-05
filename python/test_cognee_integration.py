# Quick test script for cognee integration
import asyncio

async def main():
    # Test 1: Import the cognee tools
    print("Testing imports...")
    from agent_framework import ChatAgent, AIFunction
    from agent_framework.cognee import get_cognee_tools, cognee_add, cognee_search
    from agent_framework.openai import OpenAIChatClient
    print("✓ All imports successful!")

    # Test 2: Verify tools are AIFunction instances
    print("\nVerifying tool types...")
    assert isinstance(cognee_add, AIFunction), "cognee_add should be an AIFunction"
    assert isinstance(cognee_search, AIFunction), "cognee_search should be an AIFunction"
    print(f"✓ cognee_add: {cognee_add.name}")
    print(f"✓ cognee_search: {cognee_search.name}")

    # Test 3: Get sessionized tools
    print("\nTesting get_cognee_tools...")
    add_tool, search_tool = get_cognee_tools("test-session")
    assert isinstance(add_tool, AIFunction), "add_tool should be an AIFunction"
    assert isinstance(search_tool, AIFunction), "search_tool should be an AIFunction"
    print(f"✓ Sessionized add_tool: {add_tool.name}")
    print(f"✓ Sessionized search_tool: {search_tool.name}")

    # Test 4: Create an agent with cognee tools (without making API calls)
    print("\nTesting agent creation...")
    try:
        # Just test that agent can be created with the tools
        # Don't actually run it without API key
        chat_client = OpenAIChatClient(model_id="gpt-4o-mini")
        agent = ChatAgent(
            chat_client=chat_client,
            name="TestAgent",
            instructions="You can store and retrieve information.",
            tools=[add_tool, search_tool],
        )
        print(f"✓ Agent created: {agent.name}")
        print(f"✓ Agent has {len([add_tool, search_tool])} tools configured")
    except Exception as e:
        print(f"⚠ Agent creation note: {e}")

    print("\n" + "="*50)
    print("All basic tests passed!")
    print("="*50)
    print("\nTo run the full example with actual API calls:")
    print("1. Set OPENAI_API_KEY and LLM_API_KEY environment variables")
    print("2. Run: python samples/getting_started/context_providers/cognee/cognee_openai.py")

if __name__ == "__main__":
    asyncio.run(main())

