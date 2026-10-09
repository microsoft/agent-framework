// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Azure.Core;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

[Collection(FoundryProjectEndpointEnvFixture.Name)]
public sealed class FoundryToolboxResponseScopeTests
{
    private static readonly string s_sharedResponseId = "resp_" + new string('7', 46);

    [Fact]
    public async Task CreateAsync_ToolboxClientsAreIsolatedReusedAndDisposedPerResponseAsync()
    {
        // Arrange
        HostedCallContext.CallId = null;
        SetToolboxCacheScopeId(null);

        var openScopes = new ConcurrentBag<string>();
        var agentScopes = new ConcurrentBag<string>();
        var observedTools = new ConcurrentBag<AITool>();
        var handlers = new ConcurrentBag<TrackingHttpMessageHandler>();
        var bothConcurrentOpensEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var bothConcurrentRunsEnteredAgent = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var concurrentOpenCount = 0;
        var chatCallCount = 0;
        var openCount = 0;

        var options = new FoundryToolboxOptions
        {
            StrictMode = false,
            EndpointOverride = "https://proj.example/api/projects/proj",
        };
        options.ToolboxNames.Add("shared-toolbox");

        await using var toolboxService = new FoundryToolboxService(
            Options.Create(options),
            Mock.Of<TokenCredential>())
        {
            ToolboxOpener = async (_, _, cancellationToken) =>
            {
                var scopeId = GetToolboxCacheScopeId();
                if (scopeId is null)
                {
                    throw new InvalidOperationException("Startup has no response scope.");
                }

                if (Interlocked.Increment(ref concurrentOpenCount) == 2)
                {
                    bothConcurrentOpensEntered.TrySetResult();
                }

                await bothConcurrentOpensEntered.Task
                    .WaitAsync(TimeSpan.FromSeconds(5), cancellationToken);
                openScopes.Add(scopeId);
                var openNumber = Interlocked.Increment(ref openCount);
                var handler = new TrackingHttpMessageHandler(throwOnDispose: openNumber == 1);
                handlers.Add(handler);
                AITool tool = AIFunctionFactory.Create(() => scopeId, name: $"scoped_tool_{openNumber}");
                return new FoundryToolboxService.ToolboxOpenResult(
                    new FoundryToolboxService.CachedToolbox(
                        Client: null,
                        new HttpClient(handler),
                        [tool]),
                    Consents: null);
            },
        };
        await toolboxService.StartAsync(CancellationToken.None);

        var chatClient = new Mock<IChatClient>();
        chatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> _, ChatOptions? chatOptions, CancellationToken cancellationToken) =>
            {
                agentScopes.Add(GetToolboxCacheScopeId() ?? string.Empty);
                observedTools.Add(Assert.Single(chatOptions?.Tools ?? []));

                var callNumber = Interlocked.Increment(ref chatCallCount);
                if (callNumber == 2)
                {
                    bothConcurrentRunsEnteredAgent.TrySetResult();
                }

                return callNumber <= 2
                    ? YieldAfterAsync(bothConcurrentRunsEnteredAgent.Task, cancellationToken)
                    : ThrowAsync();
            });

        var agent = new ChatClientAgent(chatClient.Object);
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        var handler = new AgentFrameworkResponseHandler(
            services.BuildServiceProvider(),
            NullLogger<AgentFrameworkResponseHandler>.Instance,
            toolboxService);

        // Act: two responses deliberately share the same public response id. Their internally
        // generated cache scopes must still be independent, while each response reuses its one
        // deferred open when the same toolbox also appears as a request marker.
        var first = RunAsync(handler, CreateRequest(), CreateContext(callId: "call-a"));
        var second = RunAsync(handler, CreateRequest(), CreateContext(callId: "call-b"));
        await Task.WhenAll(first, second);

        // Assert: both responses opened independently, carried the same opaque scope across the
        // handler's initial lifecycle yields, and disposed their response-owned clients.
        Assert.Equal(2, openCount);
        Assert.Equal(2, openScopes.Distinct(StringComparer.Ordinal).Count());
        Assert.Equal(
            openScopes.OrderBy(static value => value, StringComparer.Ordinal),
            agentScopes.OrderBy(static value => value, StringComparer.Ordinal));
        Assert.Equal(2, observedTools.Distinct().Count());
        Assert.Equal(2, handlers.Count);
        Assert.All(handlers, static item => Assert.True(item.IsDisposed));
        Assert.Equal(0, GetActiveRequestScopeCount(toolboxService));

        // Act: an agent failure is an early terminal path. The handler may translate the exception
        // to a failed response or propagate it, but the response-owned toolbox client must be released.
        List<ResponseStreamEvent>? failedEvents = null;
        var exception = await Record.ExceptionAsync(
            async () => failedEvents = await RunAsync(
                handler,
                CreateRequest(),
                CreateContext(callId: "call-failure")));

        // Assert
        Assert.True(
            exception is InvalidOperationException
            || failedEvents?.LastOrDefault() is ResponseFailedEvent);
        Assert.Equal(3, openCount);
        Assert.Equal(3, handlers.Count);
        Assert.All(handlers, static item => Assert.True(item.IsDisposed));
        Assert.Equal(0, GetActiveRequestScopeCount(toolboxService));
    }

    private static CreateResponse CreateRequest()
    {
        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_text", text = "Hello" } },
            },
        });
        request.Tools.Add(new MCPTool("shared-toolbox")
        {
            ServerUrl = new Uri("foundry-toolbox://shared-toolbox"),
        });
        return request;
    }

    private static ResponseContext CreateContext(string callId)
    {
        var context = new Mock<ResponseContext>(s_sharedResponseId) { CallBase = true };
        context.Setup(x => x.PlatformContext).Returns(new PlatformContext("user", callId));
        context.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        context.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());
        return context.Object;
    }

    private static async Task<List<ResponseStreamEvent>> RunAsync(
        AgentFrameworkResponseHandler handler,
        CreateResponse request,
        ResponseContext context)
    {
        var events = new List<ResponseStreamEvent>();
        await foreach (var responseEvent in handler.CreateAsync(request, context, CancellationToken.None))
        {
            events.Add(responseEvent);
        }

        return events;
    }

    private static string? GetToolboxCacheScopeId() =>
        typeof(HostedCallContext)
            .GetProperty("ToolboxCacheScopeId", BindingFlags.Public | BindingFlags.Static)?
            .GetValue(null) as string;

    private static void SetToolboxCacheScopeId(string? value) =>
        typeof(HostedCallContext)
            .GetProperty("ToolboxCacheScopeId", BindingFlags.Public | BindingFlags.Static)?
            .SetValue(null, value);

    private static int GetActiveRequestScopeCount(FoundryToolboxService service)
    {
        var scopes = typeof(FoundryToolboxService)
            .GetField("_requestToolboxes", BindingFlags.Instance | BindingFlags.NonPublic)?
            .GetValue(service);
        return scopes is null
            ? -1
            : (int)scopes.GetType().GetProperty("Count")!.GetValue(scopes)!;
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> YieldAfterAsync(
        Task gate,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        await gate.WaitAsync(cancellationToken);
        yield return new ChatResponseUpdate(ChatRole.Assistant, "ok") { MessageId = "resp_msg_1" };
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> ThrowAsync()
    {
        await Task.Yield();
        throw new InvalidOperationException("Agent failed after toolbox resolution.");
#pragma warning disable CS0162 // Required to make this an async iterator.
        yield break;
#pragma warning restore CS0162
    }

    private sealed class TrackingHttpMessageHandler : HttpMessageHandler
    {
        private readonly bool _throwOnDispose;

        internal TrackingHttpMessageHandler(bool throwOnDispose = false)
        {
            this._throwOnDispose = throwOnDispose;
        }

        internal bool IsDisposed { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken) =>
            throw new NotSupportedException();

        protected override void Dispose(bool disposing)
        {
            this.IsDisposed = true;
            base.Dispose(disposing);
            if (this._throwOnDispose)
            {
                throw new InvalidOperationException("Simulated HTTP client disposal failure.");
            }
        }
    }
}
