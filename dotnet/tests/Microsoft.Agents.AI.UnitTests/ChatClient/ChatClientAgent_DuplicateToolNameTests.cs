// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains tests for the duplicate tool name validation performed by
/// <see cref="ApprovalNotRequiredFunctionBypassingChatClient"/>, exercised end to end through a
/// <see cref="ChatClientAgent"/> so that every contributor to the run's tool list is covered.
/// </summary>
public class ChatClientAgent_DuplicateToolNameTests
{
    [Fact]
    public async Task RunAsync_DuplicateNameAcrossAgentAndRunTools_ThrowsAsync()
    {
        // Arrange — the agent gates 'deploy', the run supplies an ungated tool with the same name.
        var gated = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "gated", "deploy"));
        var free = AIFunctionFactory.Create(() => "free", "deploy");

        var agent = CreateAgent(out _, agentTools: [gated]);
        var runOptions = new ChatClientAgentRunOptions(new ChatOptions { Tools = [free] });

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync([new ChatMessage(ChatRole.User, "test")], options: runOptions));
        Assert.Equal("Duplicate tool name 'deploy'. Tool names must be unique.", exception.Message);
    }

    [Fact]
    public async Task RunAsync_DuplicateNameWithinAgentTools_ThrowsAsync()
    {
        // Arrange
        var first = AIFunctionFactory.Create(() => "first", "deploy");
        var second = AIFunctionFactory.Create(() => "second", "deploy");

        var agent = CreateAgent(out _, agentTools: [first, second]);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync([new ChatMessage(ChatRole.User, "test")]));
        Assert.Equal("Duplicate tool name 'deploy'. Tool names must be unique.", exception.Message);
    }

    [Fact]
    public async Task RunAsync_DuplicateNameWithinRunTools_ThrowsAsync()
    {
        // Arrange
        var first = AIFunctionFactory.Create(() => "first", "deploy");
        var second = AIFunctionFactory.Create(() => "second", "deploy");

        var agent = CreateAgent(out _);
        var runOptions = new ChatClientAgentRunOptions(new ChatOptions { Tools = [first, second] });

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync([new ChatMessage(ChatRole.User, "test")], options: runOptions));
        Assert.Equal("Duplicate tool name 'deploy'. Tool names must be unique.", exception.Message);
    }

    [Fact]
    public async Task RunAsync_DuplicateNameAddedByContextProvider_ThrowsAsync()
    {
        // Arrange — a provider contributes a tool whose name collides with the agent's gated tool.
        var gated = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "gated", "deploy"));
        var free = AIFunctionFactory.Create(() => "free", "deploy");

        var agent = CreateAgent(out _, agentTools: [gated], contextProvider: new ToolAddingAIContextProvider(free));

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync([new ChatMessage(ChatRole.User, "test")]));
        Assert.Equal("Duplicate tool name 'deploy'. Tool names must be unique.", exception.Message);
    }

    [Fact]
    public async Task RunStreamingAsync_DuplicateNameAcrossAgentAndRunTools_ThrowsAsync()
    {
        // Arrange
        var gated = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "gated", "deploy"));
        var free = AIFunctionFactory.Create(() => "free", "deploy");

        var agent = CreateAgent(out _, agentTools: [gated]);
        var runOptions = new ChatClientAgentRunOptions(new ChatOptions { Tools = [free] });

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "test")], options: runOptions))
            {
            }
        });
        Assert.Equal("Duplicate tool name 'deploy'. Tool names must be unique.", exception.Message);
    }

    [Fact]
    public async Task RunAsync_UniqueToolNames_DoesNotThrowAsync()
    {
        // Arrange
        var gated = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "gated", "deploy"));
        var free = AIFunctionFactory.Create(() => "free", "lookup");

        var agent = CreateAgent(out var capturedOptions, agentTools: [gated]);
        var runOptions = new ChatClientAgentRunOptions(new ChatOptions { Tools = [free] });

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "test")], options: runOptions);

        // Assert
        Assert.NotNull(capturedOptions.Value);
        Assert.Equal(2, capturedOptions.Value!.Tools!.Count);
    }

    [Fact]
    public async Task RunAsync_SameToolInstanceSuppliedTwice_DoesNotThrowAsync()
    {
        // Arrange — listing one instance twice is not an ambiguous call, so it is allowed.
        var tool = AIFunctionFactory.Create(() => "result", "deploy");

        var agent = CreateAgent(out _, agentTools: [tool]);
        var runOptions = new ChatClientAgentRunOptions(new ChatOptions { Tools = [tool] });

        // Act & Assert — no exception.
        await agent.RunAsync([new ChatMessage(ChatRole.User, "test")], options: runOptions);
    }

    [Theory]
    [InlineData(false, false, false)]
    [InlineData(false, true, false)]
    [InlineData(true, false, false)]
    [InlineData(true, true, false)]
    [InlineData(false, false, true)]
    [InlineData(false, true, true)]
    [InlineData(true, false, true)]
    [InlineData(true, true, true)]
    public async Task RunAsync_DeclarationWithAdditionalImplementation_PreservesExistingBehaviorAsync(
        bool streaming, bool requiresApproval, bool disableBypassing)
    {
        // Arrange
        int invocations = 0;
        int serviceCalls = 0;
        AIFunction function = AIFunctionFactory.Create(() => { invocations++; return "result"; }, "lookup");
        var declaration = function.AsDeclarationOnly();
        if (requiresApproval)
        {
            function = new ApprovalRequiredAIFunction(function);
        }

        ChatResponse CreateResponse(ChatOptions? options)
        {
            Assert.Same(declaration, Assert.Single(options!.Tools!));
            return ++serviceCalls == 1
                ? new ChatResponse(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", "lookup")]))
                : new ChatResponse(new ChatMessage(ChatRole.Assistant, "Done"));
        }

        async IAsyncEnumerable<ChatResponseUpdate> CreateStreamingResponseAsync(ChatOptions? options)
        {
            foreach (var update in CreateResponse(options).ToChatResponseUpdates())
            {
                yield return update;
            }

            await Task.CompletedTask;
        }

        var mockClient = new Mock<IChatClient>();
        mockClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions?>(), It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> _, ChatOptions? options, CancellationToken _) =>
                Task.FromResult(CreateResponse(options)));
        mockClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions?>(), It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> _, ChatOptions? options, CancellationToken _) =>
                CreateStreamingResponseAsync(options));

        var client = new FunctionInvokingChatClient(mockClient.Object) { AdditionalTools = [function] };
        var agent = new ChatClientAgent(client, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions { Tools = [declaration] },
            DisableApprovalNotRequiredFunctionBypassing = disableBypassing
        });
        var session = await agent.CreateSessionAsync();

        async Task<List<AIContent>> RunAsync(IEnumerable<ChatMessage> messages)
        {
            if (streaming)
            {
                List<AIContent> contents = [];
                await foreach (var update in agent.RunStreamingAsync(messages, session))
                {
                    contents.AddRange(update.Contents);
                }

                return contents;
            }

            var response = await agent.RunAsync(messages, session);
            return response.Messages.SelectMany(m => m.Contents).ToList();
        }

        // Act
        var contents = await RunAsync([new ChatMessage(ChatRole.User, "Look it up")]);

        // Assert
        if (requiresApproval)
        {
            Assert.Equal(0, invocations);
            var request = Assert.Single(contents.OfType<ToolApprovalRequestContent>());
            await RunAsync([new ChatMessage(ChatRole.User, [request.CreateResponse(approved: true)])]);
        }
        else
        {
            Assert.Empty(contents.OfType<ToolApprovalRequestContent>());
            Assert.Equal("lookup", Assert.Single(contents.OfType<FunctionCallContent>()).Name);
        }

        // AdditionalTools does not override the declaration already in the request.
        Assert.Equal(0, invocations);
        Assert.Equal(requiresApproval ? 2 : 1, serviceCalls);
    }

    #region Helpers

    private static ChatClientAgent CreateAgent(
        out StrongBox<ChatOptions?> capturedOptions,
        IList<AITool>? agentTools = null,
        AIContextProvider? contextProvider = null)
    {
        var captured = new StrongBox<ChatOptions?>(null);
        capturedOptions = captured;

        var mockClient = new Mock<IChatClient>();
        mockClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, options, _) => captured.Value = options)
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, "response")]));

        mockClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> _, ChatOptions? options, CancellationToken _) =>
            {
                captured.Value = options;
                return SingleUpdateAsync();
            });

        return new ChatClientAgent(mockClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = agentTools is null ? null : new ChatOptions { Tools = agentTools },
            AIContextProviders = contextProvider is null ? null : [contextProvider]
        });
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> SingleUpdateAsync()
    {
        yield return new ChatResponseUpdate(ChatRole.Assistant, "response");
        await Task.CompletedTask;
    }

    private sealed class ToolAddingAIContextProvider(AITool tool) : AIContextProvider
    {
        protected override ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            context.AIContext.Tools = [.. context.AIContext.Tools ?? [], tool];
            return new(context.AIContext);
        }
    }

    private sealed class StrongBox<T>(T value)
    {
        public T Value { get; set; } = value;
    }

    #endregion
}
