// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace AnthropicChatCompletion.IntegrationTests;

public class AnthropicBetaChatCompletionRunStreamingTests()
    : RunStreamingTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: false, useBeta: true));

public class AnthropicBetaChatCompletionReasoningRunStreamingTests()
    : RunStreamingTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: true, useBeta: true));

public class AnthropicChatCompletionRunStreamingTests()
    : RunStreamingTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: false, useBeta: false));

public class AnthropicChatCompletionReasoningRunStreamingTests()
    : RunStreamingTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: true, useBeta: false));
