// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AnthropicChatCompletion.IntegrationTests;

public abstract class SkipAllChatClientRunStreaming(Func<AnthropicChatCompletionFixture> func) : ChatClientAgentRunStreamingTests<AnthropicChatCompletionFixture>(func)
{
    [Fact(Skip = AnthropicChatCompletionFixture.SkipReason)]
    public override Task RunWithFunctionsInvokesFunctionsAndReturnsExpectedResultsAsync()
        => base.RunWithFunctionsInvokesFunctionsAndReturnsExpectedResultsAsync();

    [Fact(Skip = AnthropicChatCompletionFixture.SkipReason)]
    public override Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync()
        => base.RunWithInstructionsAndNoMessageReturnsExpectedResultAsync();
}

public class AnthropicBetaChatCompletionChatClientAgentReasoningRunStreamingTests() : SkipAllChatClientRunStreaming(() => new(useReasoningChatModel: true, useBeta: true));

public class AnthropicBetaChatCompletionChatClientAgentRunStreamingTests() : SkipAllChatClientRunStreaming(() => new(useReasoningChatModel: false, useBeta: true));

public class AnthropicChatCompletionChatClientAgentRunStreamingTests() : SkipAllChatClientRunStreaming(() => new(useReasoningChatModel: false, useBeta: false));

public class AnthropicChatCompletionChatClientAgentReasoningRunStreamingTests() : SkipAllChatClientRunStreaming(() => new(useReasoningChatModel: true, useBeta: false));
