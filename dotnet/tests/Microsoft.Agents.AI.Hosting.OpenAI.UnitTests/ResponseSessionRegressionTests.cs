// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Moq;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Regression tests for session lifetime and ordering across Responses API requests.
/// </summary>
public sealed class ResponseSessionRegressionTests
{
    private const string AgentName = "session-regression-agent";
    private const string ToolName = "get_weather";

    [Fact]
    public async Task ApprovalContinuation_TransientAgent_UsesStableRegistrationIdentityAsync()
    {
        // Arrange
        int modelCalls = 0;
        int toolCalls = 0;
        AIFunction function = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(
            () =>
            {
                Interlocked.Increment(ref toolCalls);
                return "Sunny";
            },
            ToolName));
        Mock<IChatClient> chatClient = CreateApprovalChatClient(() => Interlocked.Increment(ref modelCalls));

        WebApplicationBuilder builder = CreateBuilder();
        builder.AddAIAgent(
                AgentName,
                (_, name) => new ChatClientAgent(chatClient.Object, name: name, tools: [function]),
                ServiceLifetime.Transient)
            .WithInMemorySessionStore(withIsolation: false);
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        app.MapOpenAIResponses();
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();

        (string responseId, JsonElement approvalEvent) = await CreatePendingApprovalAsync(
            client,
            "/v1/responses",
            includeAgentName: true);
        using StringContent approvalContent = JsonContent(CreateApprovalResponseJson(
            responseId,
            approvalEvent,
            includeAgentName: true));

        // Act
        using HttpResponseMessage response = await client.PostAsync(
            new Uri("/v1/responses", UriKind.Relative),
            approvalContent);
        string responseBody = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.True(response.IsSuccessStatusCode, responseBody);
        Assert.Equal(1, toolCalls);
        Assert.Equal(2, modelCalls);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ScopedSessionStore_IsResolvedFromExecutionScopeAsync(bool resolveAgent)
    {
        // Arrange
        WebApplicationBuilder builder = CreateBuilder(validateScopes: true);
        AIAgent agent = new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: AgentName);
        builder.AddAIAgent(AgentName, (_, _) => agent)
            .WithSessionStore(
                (_, _) => new InMemoryAgentSessionStore(),
                ServiceLifetime.Scoped,
                withIsolation: false);
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        if (resolveAgent)
        {
            app.MapOpenAIResponses();
        }
        else
        {
            app.MapOpenAIResponses(agent);
        }
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();
        string path = resolveAgent ? "/v1/responses" : $"/{AgentName}/v1/responses";
        using StringContent content = JsonContent($$"""
            {
              "agent": { "name": "{{AgentName}}" },
              "input": "hello"
            }
            """);

        // Act
        using HttpResponseMessage response = await client.PostAsync(
            new Uri(path, UriKind.Relative),
            content);

        // Assert
        response.EnsureSuccessStatusCode();
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ScopedAgent_IsResolvedFromExecutionScopeAsync(bool resolveAgent)
    {
        // Arrange
        WebApplicationBuilder builder = CreateBuilder(validateScopes: true);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent(
            AgentName,
            (_, name) => new ChatClientAgent(new TestHelpers.SimpleMockChatClient(), name: name),
            ServiceLifetime.Scoped);
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        if (resolveAgent)
        {
            app.MapOpenAIResponses();
        }
        else
        {
            app.MapOpenAIResponses(agentBuilder);
        }
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();
        string path = resolveAgent ? "/v1/responses" : $"/{AgentName}/v1/responses";
        using StringContent content = JsonContent($$"""
            {
              "agent": { "name": "{{AgentName}}" },
              "input": "hello"
            }
            """);

        // Act
        using HttpResponseMessage response = await client.PostAsync(
            new Uri(path, UriKind.Relative),
            content);

        // Assert
        response.EnsureSuccessStatusCode();
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task BackgroundExecution_KeepsScopedSessionStoreAliveThroughPersistenceAsync(bool resolveAgent)
    {
        // Arrange
        var agent = new PausingApprovalAgent();
        var storeTracker = new ScopedSessionStoreTracker();
        WebApplicationBuilder builder = CreateBuilder(validateScopes: true);
        builder.AddAIAgent(AgentName, (_, _) => agent)
            .WithSessionStore(
                (_, _) => storeTracker.CreateStore(),
                ServiceLifetime.Scoped,
                withIsolation: false);
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        if (resolveAgent)
        {
            app.MapOpenAIResponses();
        }
        else
        {
            app.MapOpenAIResponses(agent);
        }
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();
        string path = resolveAgent ? "/v1/responses" : $"/{AgentName}/v1/responses";
        string requestJson = resolveAgent
            ? $$"""
                {
                  "agent": { "name": "{{AgentName}}" },
                  "input": "hello",
                  "background": true
                }
                """
            : """
                {
                  "input": "hello",
                  "background": true
                }
                """;
        using StringContent content = JsonContent(requestJson);

        // Act
        using HttpResponseMessage response = await client.PostAsync(
            new Uri(path, UriKind.Relative),
            content);
        string responseBody = await response.Content.ReadAsStringAsync();
        response.EnsureSuccessStatusCode();
        using JsonDocument responseDocument = JsonDocument.Parse(responseBody);
        string responseId = Assert.IsType<string>(
            responseDocument.RootElement.GetProperty("id").GetString());
        TrackingSessionStore executionStore =
            await storeTracker.ExecutionStoreCreated.Task.WaitAsync(TimeSpan.FromSeconds(5));

        // Assert
        try
        {
            Assert.False(executionStore.IsDisposed);
            agent.ReleaseInitialRun();
            await WaitForResponseCompletionAsync(client, path, responseId);
            await executionStore.Disposed.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal(1, executionStore.SaveCount);
        }
        finally
        {
            agent.ReleaseInitialRun();
        }
    }

    [Fact]
    public async Task StreamingApproval_RequiresTerminalEventBeforeContinuationAsync()
    {
        // Arrange
        var agent = new PausingApprovalAgent();
        WebApplicationBuilder builder = CreateBuilder();
        builder.AddAIAgent(AgentName, (_, _) => agent)
            .WithInMemorySessionStore(withIsolation: false);
        builder.AddOpenAIResponses();

        await using WebApplication app = builder.Build();
        app.MapOpenAIResponses(agent);
        await app.StartAsync();
        using HttpClient client = app.GetTestClient();
        var initialRequest = new HttpRequestMessage(HttpMethod.Post, $"/{AgentName}/v1/responses")
        {
            Content = JsonContent("""{"input":"hello","stream":true}""")
        };
        using HttpResponseMessage initialResponse = await client.SendAsync(
            initialRequest,
            HttpCompletionOption.ResponseHeadersRead);
        initialResponse.EnsureSuccessStatusCode();
        await using Stream initialStream = await initialResponse.Content.ReadAsStreamAsync();
        using var reader = new StreamReader(initialStream);
        (string responseId, JsonElement approvalEvent) = await ReadApprovalEventAsync(reader);
        string approvalJson = CreateApprovalResponseJson(
            responseId,
            approvalEvent,
            includeAgentName: false);

        // Act
        try
        {
            using HttpResponseMessage prematureResponse = await PostJsonAsync(
                client,
                $"/{AgentName}/v1/responses",
                approvalJson).WaitAsync(TimeSpan.FromSeconds(5));
            string prematureBody = await prematureResponse.Content.ReadAsStringAsync();

            // Assert
            Assert.Equal(System.Net.HttpStatusCode.BadRequest, prematureResponse.StatusCode);
            Assert.Contains("does not match a pending approval request", prematureBody, StringComparison.Ordinal);

            // Act
            agent.ReleaseInitialRun();
            string remainingEvents = await reader.ReadToEndAsync().WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Contains("response.completed", remainingEvents, StringComparison.Ordinal);
            using HttpResponseMessage approvalResponse = await PostJsonAsync(
                client,
                $"/{AgentName}/v1/responses",
                approvalJson).WaitAsync(TimeSpan.FromSeconds(5));
            string approvalBody = await approvalResponse.Content.ReadAsStringAsync();

            // Assert
            Assert.True(approvalResponse.IsSuccessStatusCode, approvalBody);
        }
        finally
        {
            agent.ReleaseInitialRun();
        }
    }

    private static WebApplicationBuilder CreateBuilder(bool validateScopes = false)
    {
        var options = new WebApplicationOptions
        {
            EnvironmentName = validateScopes ? Environments.Development : Environments.Production
        };
        WebApplicationBuilder builder = WebApplication.CreateBuilder(options);
        builder.WebHost.UseTestServer();
        return builder;
    }

    private static Mock<IChatClient> CreateApprovalChatClient(Func<int> nextCall)
    {
        Mock<IChatClient> chatClient = new();
        chatClient
            .Setup(client => client.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                AIContent content = nextCall() == 1
                    ? new FunctionCallContent("call-1", ToolName)
                    : new TextContent("Decision processed");
                return new ChatResponse([
                    new ChatMessage(ChatRole.Assistant, [content])
                ]).ToChatResponseUpdates().ToAsyncEnumerable();
            });
        return chatClient;
    }

    private static async Task<(string ResponseId, JsonElement ApprovalEvent)> CreatePendingApprovalAsync(
        HttpClient client,
        string path,
        bool includeAgentName)
    {
        string agentProperty = includeAgentName
            ? $$""" "agent": { "name": "{{AgentName}}" },"""
            : string.Empty;
        using StringContent content = JsonContent($$"""
            {
              {{agentProperty}}
              "input": "hello",
              "stream": true
            }
            """);
        using HttpResponseMessage response = await client.PostAsync(
            new Uri(path, UriKind.Relative),
            content);
        response.EnsureSuccessStatusCode();

        List<JsonElement> events = ParseSseEvents(await response.Content.ReadAsStringAsync());
        JsonElement approvalEvent = Assert.Single(events,
            item => item.GetProperty("type").GetString() == "response.function_approval.requested");
        string responseId = events.Last().GetProperty("response").GetProperty("id").GetString()!;
        return (responseId, approvalEvent);
    }

    private static string CreateApprovalResponseJson(
        string responseId,
        JsonElement approvalEvent,
        bool includeAgentName)
    {
        string agentProperty = includeAgentName
            ? $$""" "agent": { "name": "{{AgentName}}" },"""
            : string.Empty;
        return $$"""
            {
              {{agentProperty}}
              "previous_response_id": {{JsonSerializer.Serialize(responseId)}},
              "input": [{
                "type": "message",
                "role": "user",
                "content": [{
                  "type": "function_approval_response",
                  "request_id": {{approvalEvent.GetProperty("request_id").GetRawText()}},
                  "approved": true,
                  "function_call": {{approvalEvent.GetProperty("function_call").GetRawText()}}
                }]
              }]
            }
            """;
    }

    private static async Task<(string ResponseId, JsonElement ApprovalEvent)> ReadApprovalEventAsync(
        StreamReader reader)
    {
        string? responseId = null;
        while (await reader.ReadLineAsync() is { } line)
        {
            if (!line.StartsWith("data: ", StringComparison.Ordinal))
            {
                continue;
            }

            using JsonDocument document = JsonDocument.Parse(line["data: ".Length..]);
            JsonElement item = document.RootElement;
            string? type = item.GetProperty("type").GetString();
            if (type == "response.created")
            {
                responseId = item.GetProperty("response").GetProperty("id").GetString();
            }
            else if (type == "response.function_approval.requested")
            {
                return (Assert.IsType<string>(responseId), item.Clone());
            }
        }

        throw new InvalidOperationException("The stream ended before an approval request was emitted.");
    }

    private static List<JsonElement> ParseSseEvents(string content)
    {
        var events = new List<JsonElement>();
        foreach (string line in content.Split('\n'))
        {
            if (!line.StartsWith("data: ", StringComparison.Ordinal))
            {
                continue;
            }

            using JsonDocument document = JsonDocument.Parse(line["data: ".Length..]);
            events.Add(document.RootElement.Clone());
        }

        return events;
    }

    private static StringContent JsonContent(string json) =>
        new(json, Encoding.UTF8, "application/json");

    private static async Task<HttpResponseMessage> PostJsonAsync(
        HttpClient client,
        string path,
        string json)
    {
        using StringContent content = JsonContent(json);
        return await client.PostAsync(new Uri(path, UriKind.Relative), content);
    }

    private static async Task WaitForResponseCompletionAsync(
        HttpClient client,
        string path,
        string responseId)
    {
        for (int attempt = 0; attempt < 100; attempt++)
        {
            using HttpResponseMessage response = await client.GetAsync(
                new Uri($"{path}/{responseId}", UriKind.Relative));
            string responseBody = await response.Content.ReadAsStringAsync();
            response.EnsureSuccessStatusCode();
            using JsonDocument document = JsonDocument.Parse(responseBody);
            string? status = document.RootElement.GetProperty("status").GetString();
            if (status == "completed")
            {
                return;
            }

            if (status is "failed" or "cancelled" or "incomplete")
            {
                throw new InvalidOperationException(
                    $"Background response entered terminal status '{status}'.");
            }

            await Task.Delay(TimeSpan.FromMilliseconds(20));
        }

        throw new TimeoutException("Background response did not complete.");
    }

    private sealed class PausingApprovalAgent : AIAgent
    {
        private readonly TaskCompletionSource _releaseInitialRun =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public override string Name => AgentName;

        public void ReleaseInitialRun() => this._releaseInitialRun.TrySetResult();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            new(new TestSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            new(session.StateBag.Serialize());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            new(new TestSession(AgentSessionStateBag.Deserialize(serializedState)));

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException("This regression test uses streaming execution.");

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            if (messages.SelectMany(message => message.Contents).OfType<ToolApprovalResponseContent>().Any())
            {
                yield return new AgentResponseUpdate(ChatRole.Assistant, "Decision processed");
                yield break;
            }

            yield return new AgentResponseUpdate
            {
                Role = ChatRole.Assistant,
                Contents = [
                    new ToolApprovalRequestContent(
                        "request-1",
                        new FunctionCallContent(
                            "call-1",
                            ToolName,
                            new Dictionary<string, object?>()))
                ]
            };

            await this._releaseInitialRun.Task.WaitAsync(cancellationToken);
        }

        private sealed class TestSession : AgentSession
        {
            public TestSession()
            {
            }

            public TestSession(AgentSessionStateBag stateBag)
                : base(stateBag)
            {
            }
        }
    }

    private sealed class ScopedSessionStoreTracker
    {
        private int _executionStoreRecorded;

        public TaskCompletionSource<TrackingSessionStore> ExecutionStoreCreated { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TrackingSessionStore CreateStore() => new(this);

        public void RecordExecutionStore(TrackingSessionStore store)
        {
            if (Interlocked.Exchange(ref this._executionStoreRecorded, 1) == 0)
            {
                this.ExecutionStoreCreated.TrySetResult(store);
            }
        }
    }

    private sealed class TrackingSessionStore : AgentSessionStore, IDisposable
    {
        private readonly InMemoryAgentSessionStore _inner = new();
        private readonly ScopedSessionStoreTracker _tracker;

        public TrackingSessionStore(ScopedSessionStoreTracker tracker)
        {
            this._tracker = tracker;
        }

        public TaskCompletionSource Disposed { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public bool IsDisposed { get; private set; }

        public int SaveCount { get; private set; }

        public override ValueTask<AgentSession?> GetSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            CancellationToken cancellationToken = default)
        {
            ObjectDisposedException.ThrowIf(this.IsDisposed, this);
            this._tracker.RecordExecutionStore(this);
            return this._inner.GetSessionAsync(agent, key, cancellationToken);
        }

        public override ValueTask SaveSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            AgentSession session,
            CancellationToken cancellationToken = default)
        {
            ObjectDisposedException.ThrowIf(this.IsDisposed, this);
            this.SaveCount++;
            return this._inner.SaveSessionAsync(agent, key, session, cancellationToken);
        }

        public void Dispose()
        {
            this.IsDisposed = true;
            this.Disposed.TrySetResult();
        }
    }
}
