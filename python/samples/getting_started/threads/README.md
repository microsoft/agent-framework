# Thread Management Examples

This folder contains examples demonstrating different ways to manage conversation threads and chat message stores with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`custom_chat_message_store_thread.py`](custom_chat_message_store_thread.py) | Demonstrates how to implement a custom `ChatMessageStore` for persisting conversation history. Shows how to create a custom store with serialization/deserialization capabilities and integrate it with agents for thread management across multiple sessions. |
| [`suspend_resume_thread.py`](suspend_resume_thread.py) | Shows how to suspend and resume conversation threads, allowing you to save the state of a conversation and continue it later. This is useful for long-running conversations or when you need to persist conversation state across application restarts. |
| [`redis_chat_message_store_thread.py`](redis_chat_message_store_thread.py) | Comprehensive examples of using the Redis-backed `RedisChatMessageStore` for persistent conversation storage. Covers basic usage, user session management, conversation persistence across app restarts, thread serialization, and automatic message trimming. Requires Redis server and demonstrates production-ready patterns for scalable chat applications. |
