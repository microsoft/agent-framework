// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AnthropicChatCompletion.IntegrationTests;

public abstract class SkipAllRunStreaming(Func<AnthropicChatCompletionFixture> func) : RunStreamingTests<AnthropicChatCompletionFixture>(func)
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

public class AnthropicBetaChatCompletionRunStreamingTests()
    : SkipAllRunStreaming(() => new(useReasoningChatModel: false, useBeta: true));

public class AnthropicBetaChatCompletionReasoningRunStreamingTests()
    : SkipAllRunStreaming(() => new(useReasoningChatModel: true, useBeta: true));

public class AnthropicChatCompletionRunStreamingTests()
    : SkipAllRunStreaming(() => new(useReasoningChatModel: false, useBeta: false));

public class AnthropicChatCompletionReasoningRunStreamingTests()
    : SkipAllRunStreaming(() => new(useReasoningChatModel: true, useBeta: false));
