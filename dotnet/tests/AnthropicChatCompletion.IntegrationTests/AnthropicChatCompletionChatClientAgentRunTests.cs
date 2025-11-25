// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AnthropicChatCompletion.IntegrationTests;

public abstract class SkipAllChatClientAgentRun(Func<AnthropicChatCompletionFixture> func) : ChatClientAgentRunTests<AnthropicChatCompletionFixture>(func)
{
    [Fact(Skip = AnthropicChatCompletionFixture.SkipReason)]
    public override Task RunWithFunctionsInvokesFunctionsAndReturnsExpectedResultsAsync()
        => base.RunWithFunctionsInvokesFunctionsAndReturnsExpectedResultsAsync();

    [Fact(Skip = AnthropicChatCompletionFixture.SkipReason)]
    public override Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync()
        => base.RunWithInstructionsAndNoMessageReturnsExpectedResultAsync();
}

public class AnthropicBetaChatCompletionChatClientAgentRunTests()
    : SkipAllChatClientAgentRun(() => new(useReasoningChatModel: false, useBeta: true));

public class AnthropicBetaChatCompletionChatClientAgentReasoningRunTests()
    : SkipAllChatClientAgentRun(() => new(useReasoningChatModel: true, useBeta: true));

public class AnthropicChatCompletionChatClientAgentRunTests()
    : SkipAllChatClientAgentRun(() => new(useReasoningChatModel: false, useBeta: false));

public class AnthropicChatCompletionChatClientAgentReasoningRunTests()
    : SkipAllChatClientAgentRun(() => new(useReasoningChatModel: true, useBeta: false));
