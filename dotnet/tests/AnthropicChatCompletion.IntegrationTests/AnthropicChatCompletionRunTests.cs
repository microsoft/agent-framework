// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AnthropicChatCompletion.IntegrationTests;

public abstract class SkipAllRun(Func<AnthropicChatCompletionFixture> func) : RunTests<AnthropicChatCompletionFixture>(func)
{
    [Fact(Skip = AnthropicChatCompletionFixture.SkipReason)]
    public override Task RunWithChatMessageReturnsExpectedResultAsync() => base.RunWithChatMessageReturnsExpectedResultAsync();

    [Fact(Skip = AnthropicChatCompletionFixture.SkipReason)]
    public override Task RunWithNoMessageDoesNotFailAsync() => base.RunWithNoMessageDoesNotFailAsync();

    [Fact(Skip = AnthropicChatCompletionFixture.SkipReason)]
    public override Task RunWithChatMessagesReturnsExpectedResultAsync() => base.RunWithChatMessagesReturnsExpectedResultAsync();

    [Fact(Skip = AnthropicChatCompletionFixture.SkipReason)]
    public override Task RunWithStringReturnsExpectedResultAsync() => base.RunWithStringReturnsExpectedResultAsync();

    [Fact(Skip = AnthropicChatCompletionFixture.SkipReason)]
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
