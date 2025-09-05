# # Copyright (c) Microsoft. All rights reserved.

# import asyncio

# from agent_framework import ChatMessage
# from agent_framework.azure import AzureChatClient
# from agent_framework.workflow import WorkflowBuilder
# from azure.identity import AzureCliCredential

# """
# Step 2: Agents in a Workflow non-streaming

# This sample uses two custom executors. A Writer agent creates or edits content,
# then hands the conversation to a Reviewer agent which evaluates and finalizes the result.

# Purpose:
# Show how to wrap chat agents created by AzureChatClient inside workflow executors. Demonstrate the @handler pattern
# with typed inputs and typed WorkflowContext[T] outputs, connect executors with the fluent WorkflowBuilder, and finish
# by emitting a WorkflowCompletedEvent from the terminal node.

# Prerequisites:
# - Azure OpenAI configured for AzureChatClient with required environment variables.
# - Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
# - Basic familiarity with WorkflowBuilder, executors, edges, events, and streaming or non streaming runs.
# """


# async def main():
#     """Build and run a simple two node agent workflow: Writer then Reviewer."""
#     # Create the Azure chat client. AzureCliCredential uses your current az login.
#     chat_client = AzureChatClient(credential=AzureCliCredential())
#     writer_agent = chat_client.create_agent(
#         instructions=(
#             "You are an excellent content writer. You create new content and edit contents based on the feedback."
#         ),
#     )

#     reviewer_agent = chat_client.create_agent(
#         instructions=(
#             "You are an excellent content reviewer. You review the content and provide feedback to the writer."
#         ),
#     )

#     # Build the workflow using the fluent builder.
#     # Set the start node and connect an edge from writer to reviewer.
#     workflow = WorkflowBuilder().set_start_executor(writer_agent).add_edge(writer_agent, reviewer_agent).build()

#     # Run the workflow with the user's initial message.
#     # For foundational clarity, use run (non streaming) and print the terminal event.
#     events = await workflow.run(
#         ChatMessage(role="user", text="Create a slogan for a new electric SUV that is affordable and fun to drive.")
#     )
#     # The terminal node emits a WorkflowCompletedEvent; print its contents.
#     print(events.get_completed_event())


# if __name__ == "__main__":
#     asyncio.run(main())
