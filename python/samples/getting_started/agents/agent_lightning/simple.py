# from agent_framework import ChatAgent, ai_function
# from agent_framework.openai import OpenAIChatClient

# # Define your tools
# @ai_function
# async def check_reservation(reservation_id: str) -> str:
#     """Check reservation status"""
#     return f"Reservation {reservation_id} is confirmed"

# # Create agent with OpenAI client
# async with ChatAgent(
#     chat_client=OpenAIChatClient(ai_model_id="gpt-4"),
#     instructions=system_prompt,
#     tools=[check_reservation],
#     temperature=0.0
# ) as agent:

#     # Run conversation
#     thread = agent.get_new_thread()

#     # Initial message
#     response = await agent.run(
#         messages="Hello, I need help with my reservation",
#         thread=thread
#     )

#     # The framework handles tool calls automatically
#     # Response will include both text and tool execution results
