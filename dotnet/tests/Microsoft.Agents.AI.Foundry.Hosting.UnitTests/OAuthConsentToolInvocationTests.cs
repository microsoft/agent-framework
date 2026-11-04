// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using ModelContextProtocol.Client;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public sealed class OAuthConsentToolInvocationTests
{
    private const string ConsentLink = "https://auth.example.com/authorize?state=test";
    private const string InitialPrompt = "Find the synthetic record.";

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public async Task CreateAsync_AfterConsent_ContinuesSameConversationAsync(bool repeatConsent, bool customHistory)
    {
        // Arrange
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        using var peer = new ConsentPeer(ConsentLink);
        using var httpClient = new HttpClient(peer);
        await using var transport = CreateTransport(httpClient);
        await using var client = await McpClient.CreateAsync(transport, cancellationToken: timeout.Token);
        var modelInputs = new List<ChatMessage[]>();
        int protectedCalls = 0;
        var chatClient = new Mock<IChatClient>(MockBehavior.Loose);
        chatClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken) =>
            {
                var input = messages.ToArray();
                modelInputs.Add(input);
                ValidateModelInput(input);

                var update = modelInputs.Count == 1
                    ? new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent("call_search", "tool_search")])
                    : input[^1].Role == ChatRole.Tool && peer.SuccessfulProtectedToolCalls > 0
                        ? new ChatResponseUpdate(ChatRole.Assistant, "Protected tool succeeded.")
                        : new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent($"call_protected_{++protectedCalls}", "call_tool")]);
                update.MessageId = $"model_message_{modelInputs.Count}";
                update.FinishReason = update.Contents.OfType<FunctionCallContent>().Any() ? ChatFinishReason.ToolCalls : ChatFinishReason.Stop;
                return YieldUpdateAsync(update);
            });
        var agent = new ChatClientAgent(chatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions { Tools = [CreateTool(client, "tool_search"), CreateTool(client, "call_tool")] },
            ChatHistoryProvider = customHistory ? new InMemoryChatHistoryProvider() : null,
        });
        using var provider = CreateProvider(agent);
        var handler = new AgentFrameworkResponseHandler(provider, NullLogger<AgentFrameworkResponseHandler>.Instance);
        var history = new List<OutputItem>();
        var consentTurns = new List<List<ResponseStreamEvent>>();

        // Act
        for (int turn = 0; turn < (repeatConsent ? 2 : 1); turn++)
        {
            var events = await RunTurnAsync(handler, history, turn, timeout.Token);
            AssertNoFailure(events);
            consentTurns.Add(events);
            var incomplete = Assert.IsType<ResponseIncompleteEvent>(events[^1]);
            if (turn == 0)
            {
                history.Add(new OutputItemMessage(
                    id: "msg_initial",
                    role: MessageRole.User,
                    content: [new MessageContentInputTextContent(InitialPrompt)],
                    status: MessageStatus.Completed));
            }

            history.AddRange(incomplete.Response.Output);
        }

        peer.Authorized = true;
        var continuation = await RunTurnAsync(handler, history, consentTurns.Count, timeout.Token);

        // Assert
        AssertNoFailure(continuation);
        var completed = Assert.IsType<ResponseCompletedEvent>(continuation[^1]);
        Assert.Equal(consentTurns.Count + 1, peer.ProtectedToolCalls);
        Assert.Equal(1, peer.SuccessfulProtectedToolCalls);
        Assert.Equal(consentTurns.Count + 3, modelInputs.Count);
        foreach (var events in consentTurns)
        {
            Assert.Equal(ConsentLink, GetConsentLink(events));
            var output = Assert.IsType<ResponseIncompleteEvent>(events[^1]).Response.Output;
            AssertPairedCalls(output);
            var interrupted = Assert.Single(output.OfType<OutputItemFunctionToolCallOutput>(), o => o.CallId.StartsWith("call_protected_", StringComparison.Ordinal));
            Assert.Contains("OAuth consent", interrupted.Output.ToString(), StringComparison.Ordinal);
            Assert.DoesNotContain(ConsentLink, interrupted.Output.ToString(), StringComparison.Ordinal);
            Assert.DoesNotContain("protected result", interrupted.Output.ToString(), StringComparison.Ordinal);
        }

        var firstOutput = Assert.IsType<ResponseIncompleteEvent>(consentTurns[0][^1]).Response.Output;
        Assert.Contains(firstOutput.OfType<OutputItemFunctionToolCallOutput>(), o => o.CallId == "call_search" && o.Output.ToString().Contains("discovered", StringComparison.Ordinal));
        AssertPairedCalls(completed.Response.Output);
        var actualResult = Assert.Single(completed.Response.Output.OfType<OutputItemFunctionToolCallOutput>());
        Assert.Contains("protected result", actualResult.Output.ToString(), StringComparison.Ordinal);
        Assert.DoesNotContain(continuation, e => e is ResponseOutputItemAddedEvent { Item: OAuthConsentRequestOutputItem });
        Assert.All(consentTurns.Append(continuation), events =>
        {
            var terminal = events[^1] switch
            {
                ResponseIncompleteEvent e => e.Response.Output,
                ResponseCompletedEvent e => e.Response.Output,
                _ => throw new InvalidOperationException("Unexpected terminal event."),
            };
            Assert.Equal(terminal.Select(GetItemId), events.OfType<ResponseOutputItemDoneEvent>().Select(e => GetItemId(e.Item)));
            Assert.All(terminal, item => Assert.False(string.IsNullOrEmpty(GetItemId(item))));
        });
        Assert.Contains(modelInputs[^1].SelectMany(m => m.Contents).OfType<FunctionResultContent>(),
            r => r.CallId == "call_search" && r.Result?.ToString()?.Contains("discovered", StringComparison.Ordinal) == true);
        Assert.Single(modelInputs[^1], m => string.Equals(m.Text, InitialPrompt, StringComparison.Ordinal));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task CreateAsync_ConsentDuringToolBatch_PreservesCompletedResultsAsync(bool concurrent, bool consentFirst)
    {
        // Arrange
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        var siblingCompleted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var peer = new ConsentPeer(ConsentLink)
        {
            BeforeToolCall = concurrent ? ct => siblingCompleted.Task.WaitAsync(ct) : null,
        };
        using var httpClient = new HttpClient(peer);
        await using var transport = CreateTransport(httpClient);
        await using var client = await McpClient.CreateAsync(transport, cancellationToken: timeout.Token);
        int siblingCalls = 0;
        var sibling = AIFunctionFactory.Create(() =>
        {
            Interlocked.Increment(ref siblingCalls);
            siblingCompleted.TrySetResult();
            return "completed sibling result";
        }, "completed_tool");
        int modelCalls = 0;
        var chatClient = new Mock<IChatClient>(MockBehavior.Loose);
        chatClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken) =>
            {
                var input = messages.ToArray();
                ValidateModelInput(input);
                var calls = new FunctionCallContent[]
                {
                    new("call_sibling", sibling.Name),
                    new("call_consent", "call_tool"),
                };
                if (consentFirst)
                {
                    Array.Reverse(calls);
                }

                var update = ++modelCalls switch
                {
                    1 => new ChatResponseUpdate(ChatRole.Assistant, [.. calls]),
                    2 => new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent("call_retry", "call_tool")]),
                    _ => new ChatResponseUpdate(ChatRole.Assistant, "Protected tool succeeded."),
                };
                update.MessageId = $"model_message_{modelCalls}";
                update.FinishReason = modelCalls < 3 ? ChatFinishReason.ToolCalls : ChatFinishReason.Stop;
                return YieldUpdateAsync(update);
            });
        var agent = new ChatClientAgent(chatClient.Object, new ChatClientAgentOptions
        {
            AllowConcurrentInvocation = concurrent,
            ChatOptions = new ChatOptions { Tools = [sibling, CreateTool(client, "call_tool")] },
        });
        using var provider = CreateProvider(agent);
        var handler = new AgentFrameworkResponseHandler(provider, NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act
        var first = await RunTurnAsync(handler, [], 0, timeout.Token);
        AssertNoFailure(first);
        var incomplete = Assert.IsType<ResponseIncompleteEvent>(first[^1]);
        peer.Authorized = true;
        var second = await RunTurnAsync(handler, incomplete.Response.Output.ToArray(), 1, timeout.Token);

        // Assert
        Assert.Equal(ConsentLink, GetConsentLink(first));
        AssertPairedCalls(incomplete.Response.Output);
        var siblingOutput = Assert.Single(incomplete.Response.Output.OfType<OutputItemFunctionToolCallOutput>(), r => r.CallId == "call_sibling");
        bool siblingExecuted = concurrent || !consentFirst;
        Assert.Equal(siblingExecuted ? 1 : 0, siblingCalls);
        Assert.Equal(siblingExecuted, siblingOutput.Output.ToString().Contains("completed sibling result", StringComparison.Ordinal));
        AssertNoFailure(second);
        AssertPairedCalls(Assert.IsType<ResponseCompletedEvent>(second[^1]).Response.Output);
        Assert.Equal(3, modelCalls);
        Assert.Equal(2, peer.ProtectedToolCalls);
        Assert.Equal(1, peer.SuccessfulProtectedToolCalls);
    }

    [Fact]
    public async Task CreateAsync_ConsentWithStoredOutputEnabled_ReconcilesResultsBeforeIncompleteAsync()
    {
        // Arrange
        const string CustomInterruptedResult = "The user must authorize another tool before this call can run.";
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        using var peer = new ConsentPeer(ConsentLink);
        using var httpClient = new HttpClient(peer);
        await using var transport = CreateTransport(httpClient);
        await using var client = await McpClient.CreateAsync(transport, cancellationToken: timeout.Token);
        int trailingCalls = 0;
        var trailingTool = AIFunctionFactory.Create(() =>
        {
            Interlocked.Increment(ref trailingCalls);
            return "unexpected trailing result";
        }, "trailing_tool");
        int modelCalls = 0;
        int customInvokerCalls = 0;
        var chatClient = new Mock<IChatClient>(MockBehavior.Loose);
        chatClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken) =>
            {
                var input = messages.ToArray();
                return ++modelCalls switch
                {
                    1 => YieldUpdateAsync(new ChatResponseUpdate(
                        ChatRole.Assistant,
                        [
                            new FunctionCallContent("call_consent", "call_tool"),
                            new FunctionCallContent("call_trailing", trailingTool.Name),
                        ])
                    {
                        ConversationId = "resp_" + new string('1', 46),
                        MessageId = "model_message_1",
                        FinishReason = ChatFinishReason.ToolCalls,
                    }),
                    2 => ReconcileAsync(),
                    _ => throw new InvalidOperationException("Unexpected additional model call."),
                };

                async IAsyncEnumerable<ChatResponseUpdate> ReconcileAsync()
                {
                    Assert.Equal(ChatToolMode.None, options?.ToolMode);
                    Assert.Equal("resp_" + new string('1', 46), options?.ConversationId);
                    ValidateModelInput(input);
                    var results = input.SelectMany(m => m.Contents).OfType<FunctionResultContent>().ToArray();
                    var consentResult = Assert.Single(
                        results,
                        result => string.Equals(result.CallId, "call_consent", StringComparison.Ordinal));
                    var trailingResult = Assert.Single(
                        results,
                        result => string.Equals(result.CallId, "call_trailing", StringComparison.Ordinal));
                    Assert.Contains("OAuth consent", GetFunctionResultText(consentResult), StringComparison.Ordinal);
                    Assert.Equal(CustomInterruptedResult, GetFunctionResultText(trailingResult));

                    await Task.Yield();
                    yield return new ChatResponseUpdate(ChatRole.Assistant, "Authorization is required.")
                    {
                        ConversationId = "resp_" + new string('2', 46),
                        MessageId = "model_message_2",
                        FinishReason = ChatFinishReason.Stop,
                    };
                }
            });
        var functionClient = new FunctionInvokingChatClient(chatClient.Object)
        {
            AdditionalTools = [trailingTool],
            FunctionInvoker = async (context, cancellationToken) =>
            {
                Interlocked.Increment(ref customInvokerCalls);
                return await context.Function
                    .InvokeAsync(context.Arguments, cancellationToken)
                    .ConfigureAwait(false);
            },
        };
        var agent = new ChatClientAgent(functionClient, new ChatClientAgentOptions
        {
            UseProvidedChatClientAsIs = true,
            ChatOptions = new ChatOptions { Tools = [CreateTool(client, "call_tool")] },
        });
        using var provider = CreateProvider(
            agent,
            allowStoredOutputEnabled: true,
            oauthConsentInterruptedToolResult: CustomInterruptedResult);
        var handler = new AgentFrameworkResponseHandler(provider, NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act
        var events = await RunTurnAsync(handler, [], 0, timeout.Token);

        // Assert
        AssertNoFailure(events);
        Assert.Equal(ConsentLink, GetConsentLink(events));
        var output = Assert.IsType<ResponseIncompleteEvent>(events[^1]).Response.Output;
        AssertPairedCalls(output);
        Assert.Contains(
            output.OfType<OutputItemMessage>(),
            message => message.Content.OfType<MessageContentOutputTextContent>()
                .Any(content => string.Equals(content.Text, "Authorization is required.", StringComparison.Ordinal)));
        Assert.Equal(0, trailingCalls);
        Assert.Equal(1, customInvokerCalls);
        Assert.Equal(2, modelCalls);
    }

    [Fact]
    public async Task CreateAsync_ConsentWithStoreDisabled_RetryDoesNotDependOnPersistedOutputAsync()
    {
        // Arrange
        const string CustomInterruptedResult = "Authorization is required before this companion call can run.";
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        using var peer = new ConsentPeer(ConsentLink);
        using var httpClient = new HttpClient(peer);
        await using var transport = CreateTransport(httpClient);
        await using var client = await McpClient.CreateAsync(transport, cancellationToken: timeout.Token);
        var modelInputs = new List<ChatMessage[]>();
        int protectedCalls = 0;
        int trailingCalls = 0;
        var trailingTool = AIFunctionFactory.Create(() =>
        {
            Interlocked.Increment(ref trailingCalls);
            return "unexpected trailing result";
        }, "trailing_tool");
        var chatClient = new Mock<IChatClient>(MockBehavior.Loose);
        chatClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken) =>
            {
                var input = messages.ToArray();
                modelInputs.Add(input);
                ValidateModelInput(input);

                ChatResponseUpdate update;
                if (modelInputs.Count == 1)
                {
                    update = new ChatResponseUpdate(
                        ChatRole.Assistant,
                        [
                            new FunctionCallContent($"call_store_false_{++protectedCalls}", "call_tool"),
                            new FunctionCallContent("call_store_false_trailing", trailingTool.Name),
                        ]);
                }
                else
                {
                    update = input[^1].Role == ChatRole.Tool && peer.SuccessfulProtectedToolCalls > 0
                        ? new ChatResponseUpdate(ChatRole.Assistant, "Protected tool succeeded.")
                        : new ChatResponseUpdate(
                            ChatRole.Assistant,
                            [new FunctionCallContent($"call_store_false_{++protectedCalls}", "call_tool")]);
                }

                update.MessageId = $"model_message_{modelInputs.Count}";
                update.FinishReason = update.Contents.OfType<FunctionCallContent>().Any()
                    ? ChatFinishReason.ToolCalls
                    : ChatFinishReason.Stop;
                return YieldUpdateAsync(update);
            });
        var agent = new ChatClientAgent(chatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions { Tools = [CreateTool(client, "call_tool"), trailingTool] },
        });
        using var provider = CreateProvider(
            agent,
            oauthConsentInterruptedToolResult: CustomInterruptedResult);
        var handler = new AgentFrameworkResponseHandler(provider, NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act
        var first = await RunTurnAsync(
            handler,
            [],
            turn: 0,
            cancellationToken: timeout.Token,
            store: false,
            conversationId: null);
        peer.Authorized = true;
        var second = await RunTurnAsync(
            handler,
            [],
            turn: 1,
            cancellationToken: timeout.Token,
            store: false,
            conversationId: null);

        // Assert
        AssertNoFailure(first);
        Assert.Equal(ConsentLink, GetConsentLink(first));
        var incomplete = Assert.IsType<ResponseIncompleteEvent>(first[^1]);
        AssertPairedCalls(incomplete.Response.Output);
        var trailingResult = Assert.Single(
            incomplete.Response.Output.OfType<OutputItemFunctionToolCallOutput>(),
            result => string.Equals(result.CallId, "call_store_false_trailing", StringComparison.Ordinal));
        Assert.Equal($"\"{CustomInterruptedResult}\"", trailingResult.Output.ToString());
        Assert.Equal(0, trailingCalls);

        AssertNoFailure(second);
        var completed = Assert.IsType<ResponseCompletedEvent>(second[^1]);
        AssertPairedCalls(completed.Response.Output);
        Assert.Equal(2, peer.ProtectedToolCalls);
        Assert.Equal(1, peer.SuccessfulProtectedToolCalls);
        Assert.DoesNotContain(
            modelInputs[1].SelectMany(message => message.Contents).OfType<FunctionResultContent>(),
            result => string.Equals(result.CallId, "call_store_false_1", StringComparison.Ordinal));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task CreateAsync_ConsentBeforeAdditionalOrUnknownTool_SkipsTrailingCallAsync(bool useAdditionalTool)
    {
        // Arrange
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        using var peer = new ConsentPeer(ConsentLink);
        using var httpClient = new HttpClient(peer);
        await using var transport = CreateTransport(httpClient);
        await using var client = await McpClient.CreateAsync(transport, cancellationToken: timeout.Token);
        int trailingCalls = 0;
        var trailingTool = AIFunctionFactory.Create(() =>
        {
            Interlocked.Increment(ref trailingCalls);
            return "unexpected trailing result";
        }, "trailing_tool");
        int modelCalls = 0;
        var chatClient = new Mock<IChatClient>(MockBehavior.Loose);
        chatClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                var update = ++modelCalls == 1
                    ? new ChatResponseUpdate(ChatRole.Assistant,
                    [
                        new FunctionCallContent("call_consent", "call_tool"),
                        new FunctionCallContent("call_trailing", trailingTool.Name),
                    ])
                    : new ChatResponseUpdate(ChatRole.Assistant, "Unexpected continuation.");
                update.MessageId = $"model_message_{modelCalls}";
                update.FinishReason = modelCalls == 1 ? ChatFinishReason.ToolCalls : ChatFinishReason.Stop;
                return YieldUpdateAsync(update);
            });
        var functionClient = new FunctionInvokingChatClient(chatClient.Object)
        {
            AdditionalTools = useAdditionalTool ? [trailingTool] : null,
            TerminateOnUnknownCalls = false,
        };
        var agent = new ChatClientAgent(functionClient, new ChatClientAgentOptions
        {
            UseProvidedChatClientAsIs = true,
            ChatOptions = new ChatOptions { Tools = [CreateTool(client, "call_tool")] },
        });
        using var provider = CreateProvider(agent);
        var handler = new AgentFrameworkResponseHandler(provider, NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act
        var events = await RunTurnAsync(handler, [], 0, timeout.Token);

        // Assert
        AssertNoFailure(events);
        Assert.Equal(ConsentLink, GetConsentLink(events));
        var output = Assert.IsType<ResponseIncompleteEvent>(events[^1]).Response.Output;
        AssertPairedCalls(output);
        var trailingResult = Assert.Single(
            output.OfType<OutputItemFunctionToolCallOutput>(),
            result => result.CallId == "call_trailing");
        Assert.Contains("not executed because another tool requires OAuth consent", trailingResult.Output.ToString(), StringComparison.Ordinal);
        Assert.Equal(0, trailingCalls);
        Assert.Equal(1, modelCalls);
    }

    [Fact]
    public async Task CreateAsync_ConcurrentConsentBatch_EmitsEveryConsentRequirementAsync()
    {
        // Arrange
        const string OtherConsentLink = "https://auth.example.com/authorize?state=other";
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        var bothCallsEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        int callsEntered = 0;
        using var firstPeer = new ConsentPeer(ConsentLink) { BeforeToolCall = WaitForBothCallsAsync };
        using var secondPeer = new ConsentPeer(OtherConsentLink) { BeforeToolCall = WaitForBothCallsAsync };
        using var firstHttpClient = new HttpClient(firstPeer);
        using var secondHttpClient = new HttpClient(secondPeer);
        await using var firstTransport = CreateTransport(firstHttpClient);
        await using var secondTransport = CreateTransport(secondHttpClient);
        await using var firstClient = await McpClient.CreateAsync(firstTransport, cancellationToken: timeout.Token);
        await using var secondClient = await McpClient.CreateAsync(secondTransport, cancellationToken: timeout.Token);
        int modelCalls = 0;
        var chatClient = new Mock<IChatClient>(MockBehavior.Loose);
        chatClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                var update = ++modelCalls == 1
                    ? new ChatResponseUpdate(ChatRole.Assistant,
                    [
                        new FunctionCallContent("call_first", "first_tool"),
                        new FunctionCallContent("call_second", "second_tool"),
                    ])
                    : new ChatResponseUpdate(ChatRole.Assistant, "Unexpected continuation.");
                update.MessageId = $"model_message_{modelCalls}";
                update.FinishReason = modelCalls == 1 ? ChatFinishReason.ToolCalls : ChatFinishReason.Stop;
                return YieldUpdateAsync(update);
            });
        var agent = new ChatClientAgent(chatClient.Object, new ChatClientAgentOptions
        {
            AllowConcurrentInvocation = true,
            ChatOptions = new ChatOptions
            {
                Tools =
                [
                    CreateTool(firstClient, "first_tool"),
                    CreateTool(secondClient, "second_tool"),
                ],
            },
        });
        using var provider = CreateProvider(agent);
        var handler = new AgentFrameworkResponseHandler(provider, NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act
        var events = await RunTurnAsync(handler, [], 0, timeout.Token);

        // Assert
        AssertNoFailure(events);
        var output = Assert.IsType<ResponseIncompleteEvent>(events[^1]).Response.Output;
        AssertPairedCalls(output);
        var consents = events
            .OfType<ResponseOutputItemAddedEvent>()
            .Select(e => e.Item)
            .OfType<OAuthConsentRequestOutputItem>()
            .ToArray();
        Assert.Equal(2, consents.Length);
        Assert.Contains(consents, consent => string.Equals(consent.ConsentLink, ConsentLink, StringComparison.Ordinal));
        Assert.Contains(consents, consent => string.Equals(consent.ConsentLink, OtherConsentLink, StringComparison.Ordinal));
        Assert.Equal(1, firstPeer.ToolCalls);
        Assert.Equal(1, secondPeer.ToolCalls);
        Assert.Equal(1, modelCalls);

        async Task WaitForBothCallsAsync(CancellationToken cancellationToken)
        {
            if (Interlocked.Increment(ref callsEntered) == 2)
            {
                bothCallsEntered.TrySetResult();
            }

            await bothCallsEntered.Task.WaitAsync(cancellationToken);
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task CreateAsync_ConsentOnApprovedTool_PreservesApprovalRequirementAsync(bool approved)
    {
        // Arrange
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        using var peer = new ConsentPeer(ConsentLink);
        using var httpClient = new HttpClient(peer);
        await using var transport = CreateTransport(httpClient);
        await using var client = await McpClient.CreateAsync(transport, cancellationToken: timeout.Token);
        int modelCalls = 0;
        var chatClient = new Mock<IChatClient>(MockBehavior.Loose);
        chatClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken) =>
            {
                ValidateModelInput(messages);
                var update = new ChatResponseUpdate(ChatRole.Assistant,
                    [new FunctionCallContent($"call_approval_{++modelCalls}", "call_tool")])
                {
                    MessageId = $"model_message_{modelCalls}",
                    FinishReason = ChatFinishReason.ToolCalls,
                };
                return YieldUpdateAsync(update);
            });
        var agent = new ChatClientAgent(chatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions { Tools = [new ApprovalRequiredAIFunction(CreateTool(client, "call_tool"))] },
        });
        using var provider = CreateProvider(agent);
        var handler = new AgentFrameworkResponseHandler(provider, NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act
        var first = await RunTurnAsync(handler, [], 0, timeout.Token);
        AssertNoFailure(first);
        var firstOutput = Assert.IsType<ResponseCompletedEvent>(first[^1]).Response.Output;
        var approval = Assert.Single(firstOutput.OfType<OutputItemMcpApprovalRequest>());
        Assert.Equal(0, peer.ToolCalls);
        var decision = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "mcp_approval_response", approval_request_id = approval.Id, approve = approved },
        });
        var second = await RunTurnAsync(handler, firstOutput.ToArray(), 1, timeout.Token, decision);

        // Assert
        AssertNoFailure(second);
        if (!approved)
        {
            Assert.IsType<ResponseCompletedEvent>(second[^1]);
            Assert.DoesNotContain(second, e => e is ResponseOutputItemAddedEvent { Item: OAuthConsentRequestOutputItem });
            Assert.Equal(0, peer.ToolCalls);
            return;
        }

        Assert.Equal(ConsentLink, GetConsentLink(second));
        var interrupted = Assert.IsType<ResponseIncompleteEvent>(second[^1]).Response.Output;
        AssertPairedCalls(interrupted);
        Assert.Equal(1, peer.ToolCalls);
        Assert.Equal(1, modelCalls);

        peer.Authorized = true;
        var historyDecision = new OutputItemMcpApprovalResponseResource(
            id: "approval_decision",
            approvalRequestId: approval.Id,
            approve: true);
        var third = await RunTurnAsync(handler, [.. firstOutput, historyDecision, .. interrupted], 2, timeout.Token);
        AssertNoFailure(third);
        var thirdOutput = Assert.IsType<ResponseCompletedEvent>(third[^1]).Response.Output;
        var nextApproval = Assert.Single(thirdOutput.OfType<OutputItemMcpApprovalRequest>());
        Assert.NotEqual(approval.Id, nextApproval.Id);
        Assert.Equal(1, peer.ToolCalls);
        Assert.Equal(0, peer.SuccessfulProtectedToolCalls);
    }

    [Theory]
    [InlineData("graph-retrieval___SearchInternalKnowledge")]
    [InlineData("call_tool")]
    public async Task CreateAsync_ToolRequiresConsentAfterStreamingOutput_SurfacesConsentAsync(string toolName)
    {
        // Arrange
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        using var peer = new ConsentPeer(ConsentLink);
        using var httpClient = new HttpClient(peer);
        await using var transport = CreateTransport(httpClient);
        await using var client = await McpClient.CreateAsync(transport, cancellationToken: timeout.Token);

        // Act
        var (events, modelCalls) = await RunAsync(client, toolName, timeout.Token);

        // Assert
        Assert.Equal(1, peer.ToolCalls);
        var added = Assert.Single(events.OfType<ResponseOutputItemAddedEvent>(), e => e.Item is OAuthConsentRequestOutputItem);
        var consent = Assert.IsType<OAuthConsentRequestOutputItem>(added.Item);
        Assert.Equal(ConsentLink, consent.ConsentLink);
        Assert.Equal(toolName, consent.ServerLabel);
        var done = Assert.Single(events.OfType<ResponseOutputItemDoneEvent>(), e => e.Item is OAuthConsentRequestOutputItem);
        Assert.Equal(consent.Id, Assert.IsType<OAuthConsentRequestOutputItem>(done.Item).Id);
        Assert.IsType<ResponseIncompleteEvent>(events[^1]);
        Assert.Equal(1, modelCalls);
    }

    [Fact]
    public async Task CreateAsync_ConsentWithoutStructuredDetail_UsesMessageUrlAsync()
    {
        // Arrange
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        using var peer = new ConsentPeer(ConsentLink, includeDetail: false);
        using var httpClient = new HttpClient(peer);
        await using var transport = CreateTransport(httpClient);
        await using var client = await McpClient.CreateAsync(transport, cancellationToken: timeout.Token);

        // Act
        var (events, _) = await RunAsync(client, "call_tool", timeout.Token);

        // Assert
        var added = Assert.Single(events.OfType<ResponseOutputItemAddedEvent>(), e => e.Item is OAuthConsentRequestOutputItem);
        Assert.Equal(ConsentLink, Assert.IsType<OAuthConsentRequestOutputItem>(added.Item).ConsentLink);
    }

    [Theory]
    [InlineData(null)]
    [InlineData(42)]
    [InlineData("http://auth.example.com/authorize")]
    public async Task CreateAsync_InvalidStructuredConsentDetail_FailsWithoutUsingMessageUrlAsync(object? detail)
    {
        // Arrange
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        using var peer = new ConsentPeer(ConsentLink) { ErrorDetail = detail };
        using var httpClient = new HttpClient(peer);
        await using var transport = CreateTransport(httpClient);
        await using var client = await McpClient.CreateAsync(transport, cancellationToken: timeout.Token);

        // Act
        var (events, modelCalls) = await RunAsync(client, "call_tool", timeout.Token);

        // Assert
        Assert.DoesNotContain(events, e => e is ResponseOutputItemAddedEvent { Item: OAuthConsentRequestOutputItem });
        var failed = Assert.IsType<ResponseFailedEvent>(events[^1]);
        Assert.Contains("consent link policy", failed.Response.Error.Message);
        Assert.DoesNotContain(ConsentLink, failed.Response.Error.Message);
        Assert.Equal(1, modelCalls);
    }

    [Fact]
    public async Task CreateAsync_ConcurrentConsentRequests_KeepTheirOwnLinksAndCancellationAsync()
    {
        // Arrange
        const string OtherConsentLink = "https://auth.example.com/authorize?state=other";
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        var bothCallsEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        int callsEntered = 0;
        using var firstPeer = new ConsentPeer(ConsentLink) { BeforeToolCall = WaitForBothCallsAsync };
        using var secondPeer = new ConsentPeer(OtherConsentLink) { BeforeToolCall = WaitForBothCallsAsync };
        using var firstHttpClient = new HttpClient(firstPeer);
        using var secondHttpClient = new HttpClient(secondPeer);
        await using var firstTransport = CreateTransport(firstHttpClient);
        await using var secondTransport = CreateTransport(secondHttpClient);
        await using var firstClient = await McpClient.CreateAsync(firstTransport, cancellationToken: timeout.Token);
        await using var secondClient = await McpClient.CreateAsync(secondTransport, cancellationToken: timeout.Token);
        using var callerCancellation = new CancellationTokenSource();
        var callerState = new RequestConsentState { CancellationSource = callerCancellation };
        var previousState = McpConsentContext.Current.Value;
        McpConsentContext.Current.Value = callerState;
        try
        {
            // Act
            var results = await Task.WhenAll(
                RunAsync(firstClient, "call_tool", timeout.Token),
                RunAsync(secondClient, "call_tool", timeout.Token));

            // Assert
            Assert.Equal(ConsentLink, GetConsentLink(results[0].Events));
            Assert.Equal(OtherConsentLink, GetConsentLink(results[1].Events));
            Assert.All(results, result =>
            {
                Assert.IsType<ResponseIncompleteEvent>(result.Events[^1]);
                Assert.Equal(1, result.ModelCalls);
            });
            Assert.Same(callerState, McpConsentContext.Current.Value);
            Assert.Empty(callerState.GetPendingConsents());
            Assert.False(callerCancellation.IsCancellationRequested);
        }
        finally
        {
            McpConsentContext.Current.Value = previousState;
        }

        async Task WaitForBothCallsAsync(CancellationToken cancellationToken)
        {
            if (Interlocked.Increment(ref callsEntered) == 2)
            {
                bothCallsEntered.TrySetResult();
            }

            await bothCallsEntered.Task.WaitAsync(cancellationToken);
        }
    }

    private static string GetConsentLink(List<ResponseStreamEvent> events) =>
        Assert.IsType<OAuthConsentRequestOutputItem>(
            Assert.Single(events.OfType<ResponseOutputItemAddedEvent>(), e => e.Item is OAuthConsentRequestOutputItem).Item).ConsentLink;

    private static HttpClientTransport CreateTransport(HttpClient httpClient) => new(
        new HttpClientTransportOptions
        {
            Endpoint = new Uri("https://toolbox.example.com/mcp"),
            TransportMode = HttpTransportMode.StreamableHttp,
        },
        httpClient);

    private static ConsentAwareMcpClientAIFunction CreateTool(McpClient client, string toolName) => new(
        new McpClientTool(client, new ModelContextProtocol.Protocol.Tool
        {
            Name = toolName,
            Description = "Invokes the test tool.",
            InputSchema = JsonSerializer.SerializeToElement(new { type = "object" }),
        }, serializerOptions: null),
        "test-toolbox");

    private static ServiceProvider CreateProvider(
        AIAgent agent,
        bool allowStoredOutputEnabled = false,
        string? oauthConsentInterruptedToolResult = null)
    {
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton(agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var options = new FoundryResponsesOptions
        {
            AllowStoredOutputEnabled = allowStoredOutputEnabled,
        };
        if (oauthConsentInterruptedToolResult is not null)
        {
            options.OAuthConsentInterruptedToolResult = oauthConsentInterruptedToolResult;
        }

        services.AddSingleton(
            Options.Create(options));
        return services.BuildServiceProvider();
    }

    private static async Task<List<ResponseStreamEvent>> RunTurnAsync(
        AgentFrameworkResponseHandler handler,
        IReadOnlyList<OutputItem> history,
        int turn,
        CancellationToken cancellationToken,
        BinaryData? input = null,
        bool store = true,
        string? conversationId = "conv-oauth-continuation")
    {
        var request = new CreateResponse
        {
            Model = "test",
            Background = false,
            Store = store,
            Stream = true,
            Conversation = conversationId is null
                ? null
                : BinaryData.FromString($"\"{conversationId}\""),
            Input = input ?? BinaryData.FromObjectAsJson(turn == 0 ? InitialPrompt : "Continue after authorization."),
        };
        var context = new Mock<ResponseContext>("resp_" + new string((char)('0' + turn), 46)) { CallBase = true };
        context.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>())).ReturnsAsync(history);
        context.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<Item>());
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(request, context.Object, cancellationToken))
        {
            events.Add(evt);
        }

        return events;
    }

    private static void AssertNoFailure(IEnumerable<ResponseStreamEvent> events)
    {
        var failure = events.OfType<ResponseFailedEvent>().FirstOrDefault();
        Assert.True(failure is null, failure?.Response.Error.Message);
    }

    private static void AssertPairedCalls(IEnumerable<OutputItem> output)
    {
        Assert.Equal(
            output.OfType<OutputItemFunctionToolCall>().Select(c => c.CallId).Order(StringComparer.Ordinal),
            output.OfType<OutputItemFunctionToolCallOutput>().Select(r => r.CallId).Order(StringComparer.Ordinal));
    }

    private static string GetFunctionResultText(FunctionResultContent result) => result.Result switch
    {
        JsonElement { ValueKind: JsonValueKind.String } element => element.GetString()!,
        _ => result.Result?.ToString() ?? string.Empty,
    };

    private static void ValidateModelInput(IEnumerable<ChatMessage> messages)
    {
        var contents = messages.SelectMany(m => m.Contents).ToArray();
        var resultIds = contents.OfType<FunctionResultContent>().Select(r => r.CallId).ToHashSet(StringComparer.Ordinal);
        var unmatched = contents.OfType<FunctionCallContent>().FirstOrDefault(c => !resultIds.Contains(c.CallId));
        if (unmatched is not null)
        {
            throw new InvalidOperationException($"No tool output found for function call {unmatched.CallId}.");
        }
    }

    private static string GetItemId(OutputItem item) => item switch
    {
        OutputItemFunctionToolCall call => call.Id,
        OutputItemFunctionToolCallOutput result => result.Id,
        OutputItemMessage message => message.Id,
        OAuthConsentRequestOutputItem consent => consent.Id,
        OutputItemMcpApprovalRequest approval => approval.Id,
        _ => throw new InvalidOperationException("Unexpected output item."),
    };

    private static async Task<(List<ResponseStreamEvent> Events, int ModelCalls)> RunAsync(
        McpClient client,
        string toolName,
        CancellationToken cancellationToken)
    {
        var tool = CreateTool(client, toolName);
        var modelCalls = 0;
        var chatClient = new Mock<IChatClient>(MockBehavior.Loose);
        chatClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(() => Interlocked.Increment(ref modelCalls) == 1
                ? YieldUpdateAsync(new ChatResponseUpdate(
                    ChatRole.Assistant,
                    [new FunctionCallContent("call_test", toolName)])
                {
                    MessageId = "tool_message",
                    FinishReason = ChatFinishReason.ToolCalls,
                })
                : YieldUpdateAsync(new ChatResponseUpdate(ChatRole.Assistant, "The tool failed.")
                {
                    MessageId = "final_message",
                    FinishReason = ChatFinishReason.Stop,
                }));

        var agent = new ChatClientAgent(chatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions { Tools = [tool] },
        });
        using var provider = CreateProvider(agent);
        var handler = new AgentFrameworkResponseHandler(provider, NullLogger<AgentFrameworkResponseHandler>.Instance);
        var context = new Mock<ResponseContext>(MockBehavior.Loose, "resp_" + new string('0', 46)) { CallBase = true };
        context.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<OutputItem>());
        context.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<Item>());
        var events = new List<ResponseStreamEvent>();
        await foreach (var evt in handler.CreateAsync(new CreateResponse { Model = "test" }, context.Object, cancellationToken))
        {
            events.Add(evt);
        }

        return (events, modelCalls);
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> YieldUpdateAsync(ChatResponseUpdate update)
    {
        await Task.Yield();
        yield return update;
    }

    private sealed class ConsentPeer(string consentLink, bool includeDetail = true) : HttpMessageHandler
    {
        public int ToolCalls { get; private set; }

        public int ProtectedToolCalls { get; private set; }

        public int SuccessfulProtectedToolCalls { get; private set; }

        public bool Authorized { get; set; }

        public object? ErrorDetail { get; set; } = consentLink;

        public Func<CancellationToken, Task>? BeforeToolCall { get; init; }

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            using var body = JsonDocument.Parse(
                await request.Content!.ReadAsStringAsync(cancellationToken));
            var root = body.RootElement;
            if (!root.TryGetProperty("id", out var id))
            {
                return new HttpResponseMessage(HttpStatusCode.Accepted);
            }

            string json;
            switch (root.GetProperty("method").GetString())
            {
                case "server/discover":
                    json = JsonSerializer.Serialize(new
                    {
                        jsonrpc = "2.0",
                        id,
                        error = new { code = -32601, message = "Method not found" },
                    });
                    break;
                case "initialize":
                    json = JsonSerializer.Serialize(new
                    {
                        jsonrpc = "2.0",
                        id,
                        result = new
                        {
                            protocolVersion = "2025-03-26",
                            capabilities = new { tools = new { } },
                            serverInfo = new { name = "consent-test", version = "1.0" },
                        },
                    });
                    break;
                case "tools/call":
                    this.ToolCalls++;
                    var name = root.GetProperty("params").GetProperty("name").GetString();
                    bool discovery = string.Equals(name, "tool_search", StringComparison.Ordinal);
                    if (discovery || this.Authorized)
                    {
                        if (!discovery)
                        {
                            this.ProtectedToolCalls++;
                            this.SuccessfulProtectedToolCalls++;
                        }

                        json = JsonSerializer.Serialize(new
                        {
                            jsonrpc = "2.0",
                            id,
                            result = new
                            {
                                content = new[] { new { type = "text", text = discovery ? "discovered call_tool" : "protected result" } },
                            },
                        });
                        break;
                    }

                    this.ProtectedToolCalls++;
                    if (this.BeforeToolCall is { } beforeToolCall)
                    {
                        await beforeToolCall(cancellationToken);
                    }

                    var data = new Dictionary<string, object?> { ["grpcStatus"] = "FailedPrecondition" };
                    if (includeDetail)
                    {
                        data["detail"] = this.ErrorDetail;
                    }

                    json = JsonSerializer.Serialize(new
                    {
                        jsonrpc = "2.0",
                        id,
                        error = new
                        {
                            code = -32006,
                            message = consentLink,
                            data,
                        },
                    });
                    break;
                default:
                    throw new InvalidOperationException("Unexpected MCP method: " + root.GetProperty("method"));
            }

            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json"),
            };
        }
    }
}
