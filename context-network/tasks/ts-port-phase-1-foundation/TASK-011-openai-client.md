# Task: TASK-011 OpenAI ChatClient Implementation

**Phase**: 1  
**Priority**: High  
**Estimated Effort**: 6 hours  
**Dependencies**: TASK-002, TASK-003, TASK-004, TASK-005

## Objective
Implement OpenAIChatClient conforming to ChatClientProtocol with tool calling and streaming.

## Context References
- **Spec**: 002-typescript-feature-parity.md § FR-2, FR-11 (OpenAI)
- **Python**: `/python/packages/openai/agent_framework/openai/_client.py`

## Files to Create/Modify
- `src/providers/openai/chat-client.ts`
- `src/providers/openai/__tests__/chat-client.test.ts`

## Implementation Requirements
1. OpenAIChatClient class implementing ChatClientProtocol
2. complete() and completeStream() methods
3. Tool calling support (function_call content)
4. Streaming with SSE parsing
5. Error handling and retries
6. API key configuration

## Test Requirements
- Complete with text response
- Complete with tool calls
- Streaming responses
- Error handling
- Mock OpenAI API responses

**Coverage**: >80%

## Notes
Add dependency: `npm install openai`
