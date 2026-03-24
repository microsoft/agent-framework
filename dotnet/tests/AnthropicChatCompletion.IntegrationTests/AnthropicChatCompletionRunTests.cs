// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace AnthropicChatCompletion.IntegrationTests;

public class AnthropicBetaChatCompletionRunTests()
    : RunTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: false, useBeta: true));

public class AnthropicBetaChatCompletionReasoningRunTests()
    : RunTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: true, useBeta: true));

public class AnthropicChatCompletionRunTests()
    : RunTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: false, useBeta: false));

public class AnthropicChatCompletionReasoningRunTests()
    : RunTests<AnthropicChatCompletionFixture>(() => new(useReasoningChatModel: true, useBeta: false));
