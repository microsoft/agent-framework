// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace AnthropicChatCompletion.IntegrationTests;

public class AnthropicBetaChatCompletionChatClientAgentReasoningRunStreamingTests() : ChatClientAgentRunStreamingTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: true, useBeta: true));

public class AnthropicBetaChatCompletionChatClientAgentRunStreamingTests() : ChatClientAgentRunStreamingTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: false, useBeta: true));

public class AnthropicChatCompletionChatClientAgentRunStreamingTests() : ChatClientAgentRunStreamingTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: false, useBeta: false));

public class AnthropicChatCompletionChatClientAgentReasoningRunStreamingTests() : ChatClientAgentRunStreamingTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: true, useBeta: false));
