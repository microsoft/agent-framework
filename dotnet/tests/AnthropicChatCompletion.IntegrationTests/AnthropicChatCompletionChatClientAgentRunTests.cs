// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace AnthropicChatCompletion.IntegrationTests;

public class AnthropicBetaChatCompletionChatClientAgentRunTests()
    : ChatClientAgentRunTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: false, useBeta: true));

public class AnthropicBetaChatCompletionChatClientAgentReasoningRunTests()
    : ChatClientAgentRunTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: true, useBeta: true));

public class AnthropicChatCompletionChatClientAgentRunTests()
    : ChatClientAgentRunTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: false, useBeta: false));

public class AnthropicChatCompletionChatClientAgentReasoningRunTests()
    : ChatClientAgentRunTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: true, useBeta: false));
