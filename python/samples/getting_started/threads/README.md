# Thread Management Examples

This folder contains examples demonstrating different ways to manage conversation threads and chat message stores with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`custom_chat_message_store_thread.py`](custom_chat_message_store_thread.py) | Demonstrates how to implement a custom `ChatMessageStore` for persisting conversation history. Shows how to create a custom store with serialization/deserialization capabilities and integrate it with agents for thread management across multiple sessions. |
| [`redis_chat_message_store_thread.py`](redis_chat_message_store_thread.py) | Comprehensive examples of using the Redis-backed `RedisChatMessageStore` for persistent conversation storage. Covers basic usage, user session management, conversation persistence across app restarts, thread serialization, and automatic message trimming. Requires Redis server and demonstrates production-ready patterns for scalable chat applications. |
| [`suspend_resume_thread.py`](suspend_resume_thread.py) | Shows how to suspend and resume conversation threads, comparing service-managed threads (Azure AI) with in-memory threads (OpenAI). Demonstrates saving conversation state and continuing it later, useful for long-running conversations or persisting state across application restarts. |

## Environment Variables

Make sure to set the following environment variables before running the examples:

- `OPENAI_API_KEY`: Your OpenAI API key (required for all samples)
- `OPENAI_CHAT_MODEL_ID`: The OpenAI model to use (e.g., `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`) (required for all samples)
- `AZURE_AI_PROJECT_ENDPOINT`: Azure AI Project endpoint URL (required for service-managed thread examples)
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`: The name of your model deployment (required for service-managed thread examples)
