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
using ModelContextProtocol.Client;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public sealed class OAuthConsentToolInvocationTests
{
    private const string ConsentLink = "https://auth.example.com/authorize?state=test";

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
            Assert.Null(callerState.Pending);
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

    private static async Task<(List<ResponseStreamEvent> Events, int ModelCalls)> RunAsync(
        McpClient client,
        string toolName,
        CancellationToken cancellationToken)
    {
        var tool = new ConsentAwareMcpClientAIFunction(
            new McpClientTool(client, new ModelContextProtocol.Protocol.Tool
            {
                Name = toolName,
                Description = "Invokes the OAuth-protected tool.",
                InputSchema = JsonSerializer.SerializeToElement(new { type = "object" }),
            }, serializerOptions: null),
            "test-toolbox");
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
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        using var provider = services.BuildServiceProvider();
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
