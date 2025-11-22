// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AnthropicChatCompletion.IntegrationTests;

public abstract class SkipAllRun(Func<AnthropicChatCompletionFixture> func) : RunTests<AnthropicChatCompletionFixture>(func)
{
    [Fact(Skip = "For manual verification.")]
    public override Task RunWithChatMessageReturnsExpectedResultAsync() => base.RunWithChatMessageReturnsExpectedResultAsync();

    [Fact(Skip = "For manual verification.")]
    public override Task RunWithNoMessageDoesNotFailAsync() => base.RunWithNoMessageDoesNotFailAsync();

    [Fact(Skip = "For manual verification.")]
    public override Task RunWithChatMessagesReturnsExpectedResultAsync() => base.RunWithChatMessagesReturnsExpectedResultAsync();

    [Fact(Skip = "For manual verification.")]
    public override Task RunWithStringReturnsExpectedResultAsync() => base.RunWithStringReturnsExpectedResultAsync();

    [Fact(Skip = "For manual verification.")]
    public override Task ThreadMaintainsHistoryAsync() => base.ThreadMaintainsHistoryAsync();
}

public class AnthropicBetaChatCompletionRunTests()
    : SkipAllRun(() => new(useReasoningChatModel: false, useBeta: true));

public class AnthropicBetaChatCompletionReasoningRunTests()
    : SkipAllRun(() => new(useReasoningChatModel: true, useBeta: true));

public class AnthropicChatCompletionRunTests()
    : SkipAllRun(() => new(useReasoningChatModel: false, useBeta: false));

public class AnthropicChatCompletionReasoningRunTests()
    : SkipAllRun(() => new(useReasoningChatModel: true, useBeta: false));
