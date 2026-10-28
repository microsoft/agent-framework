// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

public class ChatClientAgent_PartialApprovalsTests
{
    [Theory]
    [InlineData(false, false, false, false, false)]
    [InlineData(false, false, false, false, true)]
    [InlineData(false, false, false, true, false)]
    [InlineData(false, false, false, true, true)]
    [InlineData(false, false, true, false, false)]
    [InlineData(false, false, true, false, true)]
    [InlineData(false, false, true, true, false)]
    [InlineData(false, false, true, true, true)]
    [InlineData(false, true, false, false, false)]
    [InlineData(false, true, false, false, true)]
    [InlineData(false, true, false, true, false)]
    [InlineData(false, true, false, true, true)]
    [InlineData(false, true, true, false, false)]
    [InlineData(false, true, true, false, true)]
    [InlineData(false, true, true, true, false)]
    [InlineData(false, true, true, true, true)]
    [InlineData(true, false, false, false, false)]
    [InlineData(true, false, false, false, true)]
    [InlineData(true, false, false, true, false)]
    [InlineData(true, false, false, true, true)]
    [InlineData(true, false, true, false, false)]
    [InlineData(true, false, true, false, true)]
    [InlineData(true, false, true, true, false)]
    [InlineData(true, false, true, true, true)]
    [InlineData(true, true, false, false, false)]
    [InlineData(true, true, false, false, true)]
    [InlineData(true, true, false, true, false)]
    [InlineData(true, true, false, true, true)]
    [InlineData(true, true, true, false, false)]
    [InlineData(true, true, true, false, true)]
    [InlineData(true, true, true, true, false)]
    [InlineData(true, true, true, true, true)]
    public async Task PartialAnswers_ReloadAndReplay_PreservesOriginalBatchAsync(bool streaming, bool approveA, bool frontend, bool approveB, bool perServicePersistence)
    {
        // Arrange
        List<string> executed = [];
        List<FunctionResultContent> received = [];
        int modelCalls = 0;
        var tool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create((string value) =>
        {
            executed.Add(value);
            return "canonical:" + value;
        }, "protected_tool"));
        var client = CreateChatClient((messages, _, _) =>
        {
            received.Clear();
            received.AddRange(messages.SelectMany(m => m.Contents).OfType<FunctionResultContent>());
            if (++modelCalls == 1)
            {
                List<AIContent> calls =
                [
                    new FunctionCallContent("call-a", "protected_tool", new Dictionary<string, object?> { ["value"] = "a" }),
                    new FunctionCallContent("call-b", "protected_tool", new Dictionary<string, object?> { ["value"] = "b" }),
                ];
                if (frontend)
                {
                    calls.Add(new FunctionCallContent("call-ui", "frontend_tool"));
                }

                return Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, calls) { MessageId = "original-batch" }]));
            }

            var ordered = messages.ToList();
            int questionIndex = ordered.FindIndex(m => m.Text == "still deciding");
            if (questionIndex >= 0 && modelCalls == 2)
            {
                Assert.True(ordered.FindLastIndex(m => m.Contents.OfType<FunctionResultContent>().Any()) < questionIndex);
            }

            return Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "complete")]));
        });
        ChatClientAgent NewAgent() => new(client, new ChatClientAgentOptions
        {
            EnablePartialApprovalResponses = true,
            RequirePerServiceCallChatHistoryPersistence = perServicePersistence,
            ChatOptions = new ChatOptions
            {
                Tools = frontend ? [tool, AIFunctionFactory.CreateDeclaration("frontend_tool", "Frontend", tool.JsonSchema)] : [tool],
            },
        });
        var agent = NewAgent();
        var session = await agent.CreateSessionAsync();
        Task<AgentResponse> RunAsync(params ChatMessage[] messages) => streaming
            ? agent.RunStreamingAsync(messages, session).ToAgentResponseAsync()
            : agent.RunAsync(messages, session);
        async Task ReloadAsync()
        {
            var json = await agent.SerializeSessionAsync(session);
            agent = NewAgent();
            session = await agent.DeserializeSessionAsync(json);
        }

        var first = await RunAsync(new ChatMessage(ChatRole.User, "Run the tools"));
        var requests = first.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToDictionary(r => r.ToolCall.CallId);
        Assert.Equal("ficc_call-a", requests["call-a"].RequestId);
        Assert.Equal("ficc_call-b", requests["call-b"].RequestId);

        // Act: answer A, persist, recreate both the agent and its native session, then replay A.
        var unanswered = await RunAsync(new ChatMessage(ChatRole.User, "still deciding"));
        Assert.Equal(requests.Count, unanswered.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().Count());
        await ReloadAsync();
        var partial = await RunAsync(new ChatMessage(ChatRole.User, [requests["call-a"].CreateResponse(approveA, "chosen-a")]));
        Assert.Empty(executed);
        Assert.Equal(1, modelCalls);
        Assert.DoesNotContain(partial.Messages.SelectMany(m => m.Contents), c => c is ToolApprovalResponseContent or FunctionResultContent);
        await ReloadAsync();
        var replay = await RunAsync(new ChatMessage(ChatRole.User, [requests["call-a"].CreateResponse(!approveA)]));
        Assert.Contains(replay.Messages.SelectMany(m => m.Contents), c => c is ToolApprovalRequestContent r && r.RequestId == "ficc_call-b");
        Assert.Empty(executed);
        var pendingB = Assert.Single(replay.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>(), r => r.RequestId == "ficc_call-b");
        var originalB = Assert.IsType<FunctionCallContent>(pendingB.ToolCall);
        Assert.Equal("call-b", originalB.CallId);
        Assert.Equal("protected_tool", originalB.Name);
        Assert.Equal("b", originalB.Arguments!["value"]?.ToString());
        if (frontend)
        {
            await RunAsync(new ChatMessage(ChatRole.Tool, [new FunctionResultContent("call-ui", "canonical:frontend")]));
            await ReloadAsync();
        }

        var final = await RunAsync(new ChatMessage(ChatRole.User,
        [
            new ToolApprovalResponseContent("ficc_call-b", approveB,
                new FunctionCallContent("forged-call", "protected_tool", new Dictionary<string, object?> { ["value"] = "wrong" })),
            requests["call-b"].CreateResponse(!approveB),
        ]));

        // Assert: canonical results refer to the original calls; replay cannot execute again.
        Assert.Equal(new[] { approveA ? "a" : null, approveB ? "b" : null }.Where(value => value is not null), executed);
        Assert.Contains(received, r => r.CallId == "call-b" && r.Result?.ToString() == (approveB ? "canonical:b" : "Tool call invocation rejected."));
        Assert.Contains(received, r => r.CallId == "call-a" && r.Result?.ToString() == (approveA ? "canonical:a" : "Tool call invocation rejected. chosen-a"));
        if (frontend)
        {
            Assert.Contains(received, r => r.CallId == "call-ui" && r.Result?.ToString() == "canonical:frontend");
        }

        Assert.DoesNotContain(final.Messages.SelectMany(m => m.Contents), c => c is ToolApprovalRequestContent);
        var persisted = (await agent.SerializeSessionAsync(session)).GetRawText();
        Assert.Contains(approveA ? "canonical:a" : "Tool call invocation rejected. chosen-a", persisted);
        Assert.Contains(approveB ? "canonical:b" : "Tool call invocation rejected.", persisted);
        Assert.Contains("call-a", persisted);
        Assert.Contains("call-b", persisted);
        if (frontend)
        {
            Assert.Contains("canonical:frontend", persisted);
            Assert.Contains("call-ui", persisted);
        }

        Assert.False(session.StateBag.TryGetValue<List<ToolApprovalRequestContent>>(ApprovalResponseBindingChatClient.StateBagKey, out _));
        Assert.False(session.StateBag.TryGetValue<List<ChatMessage>>(ApprovalResponseBindingChatClient.DecisionsStateBagKey, out _));
        await ReloadAsync();
        await RunAsync(new ChatMessage(ChatRole.User, [requests["call-b"].CreateResponse(true)]));
        Assert.Equal(new[] { approveA ? "a" : null, approveB ? "b" : null }.Where(value => value is not null), executed);
    }

    [Fact]
    public void PartialAnswers_OptionClonesAndRequiresBinding()
    {
        // Arrange
        var options = new ChatClientAgentOptions { EnablePartialApprovalResponses = true };

        // Act / Assert
        Assert.True(options.Clone().EnablePartialApprovalResponses);
        options.DisableApprovalResponseBinding = true;
        Assert.Throws<ArgumentException>(() => new ChatClientAgent(new Mock<IChatClient>().Object, options));
        Assert.False(new ChatClientAgentOptions().EnablePartialApprovalResponses);
    }

    private static IChatClient CreateChatClient(Func<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken, Task<ChatResponse>> respond)
    {
        var mock = new Mock<IChatClient>();
        mock.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions?>(), It.IsAny<CancellationToken>())).Returns(respond);
        mock.Setup(c => c.GetStreamingResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions?>(), It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken ct) => StreamAsync(messages, options, ct));
        return mock.Object;

        async IAsyncEnumerable<ChatResponseUpdate> StreamAsync(IEnumerable<ChatMessage> messages, ChatOptions? options, [EnumeratorCancellation] CancellationToken ct)
        {
            foreach (var update in (await respond(messages, options, ct)).ToChatResponseUpdates())
            {
                ct.ThrowIfCancellationRequested();
                yield return update;
            }
        }
    }
}
