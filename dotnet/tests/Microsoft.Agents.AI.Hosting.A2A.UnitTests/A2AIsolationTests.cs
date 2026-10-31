// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests;

/// <summary>
/// Verifies caller isolation for A2A runs that continue after the originating HTTP request has ended.
/// </summary>
public sealed class A2AIsolationTests : IAsyncDisposable
{
    private const string AgentName = "isolated-agent";
    private const string UserHeader = "X-Test-User";
    private const string Alice = "alice";
    private const string Bob = "bob";
    private const string AgentReply = "Detached reply";

    private readonly RecordingSessionStore _sessionStore = new();
    private WebApplication? _app;
    private HttpClient? _httpClient;

    [Fact]
    public async Task ReturnImmediately_RunCompletingAfterRequest_PreservesCallerIsolationAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        HttpClient client = await this.CreateTestServerAsync(cts.Token);
        var request = new SendMessageRequest
        {
            Message = new Message { MessageId = "request", Role = Role.User, Parts = [Part.FromText("Hello")] },
            Configuration = new SendMessageConfiguration { ReturnImmediately = true },
        };

        // Act: the request returns while the agent is still running, and the agent replies once the request has ended.
        using HttpResponseMessage response = await SendAsync(client, HttpMethod.Post, Alice, "/a2a/message:send", request, cts.Token);
        response.EnsureSuccessStatusCode();
        SendMessageResponse sendResponse = (await DeserializeAsync<SendMessageResponse>(response, cts.Token))!;
        string taskId = sendResponse.Task!.Id;

        // Assert
        await this.AssertCompletedForAliceOnlyAsync(client, taskId, cts.Token);
    }

    [Fact]
    public async Task Streaming_RunCompletingAfterClientDisconnects_PreservesCallerIsolationAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        HttpClient client = await this.CreateTestServerAsync(cts.Token);
        var request = new SendMessageRequest
        {
            Message = new Message { MessageId = "request", Role = Role.User, Parts = [Part.FromText("Hello")] },
        };

        // Act: read the first event and disconnect, and the agent replies once the request has ended.
        string taskId;
        using (var httpRequest = CreateRequest(HttpMethod.Post, Alice, "/a2a/message:stream", request))
        using (HttpResponseMessage response = await client.SendAsync(httpRequest, HttpCompletionOption.ResponseHeadersRead, cts.Token))
        {
            response.EnsureSuccessStatusCode();
            taskId = await ReadFirstStreamedTaskIdAsync(response, cts.Token);
        }

        // Assert
        await this.AssertCompletedForAliceOnlyAsync(client, taskId, cts.Token);
    }

    // Checks that the run completed for Alice, is hidden from Bob, and saved its session in Alice's partition.
    private async Task AssertCompletedForAliceOnlyAsync(HttpClient client, string taskId, CancellationToken cancellationToken)
    {
        AgentTask task = await WaitForTerminalTaskAsync(client, Alice, taskId, cancellationToken);
        Assert.Equal(TaskState.Completed, task.Status.State);
        Assert.Equal(AgentReply, Assert.Single(Assert.Single(task.Artifacts!).Parts!).Text);

        using HttpResponseMessage bobResponse = await SendAsync(client, HttpMethod.Get, Bob, $"/a2a/tasks/{taskId}", body: null, cancellationToken);
        Assert.Equal(HttpStatusCode.NotFound, bobResponse.StatusCode);

        // The session is saved after the task completes, so wait for the save before checking its partition.
        AgentSessionStoreKey savedKey = await this._sessionStore.Saved.Task.WaitAsync(cancellationToken);
        Assert.Equal(task.ContextId, savedKey.SessionId);
        Assert.NotNull(savedKey.Partitions);
        Assert.Equal(Alice, savedKey.Partitions["isolation"]);
    }

    private static async Task<AgentTask> WaitForTerminalTaskAsync(HttpClient client, string principal, string taskId, CancellationToken cancellationToken)
    {
        while (true)
        {
            using HttpResponseMessage response = await SendAsync(client, HttpMethod.Get, principal, $"/a2a/tasks/{taskId}", body: null, cancellationToken);
            response.EnsureSuccessStatusCode();
            AgentTask task = (await DeserializeAsync<AgentTask>(response, cancellationToken))!;
            if (task.Status.State.IsTerminal())
            {
                return task;
            }

            await Task.Delay(TimeSpan.FromMilliseconds(20), cancellationToken);
        }
    }

    private static async Task<string> ReadFirstStreamedTaskIdAsync(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        using var reader = new StreamReader(await response.Content.ReadAsStreamAsync(cancellationToken));
        while (await reader.ReadLineAsync(cancellationToken) is { } line)
        {
            if (line.StartsWith("data:", StringComparison.Ordinal))
            {
                StreamResponse streamed = JsonSerializer.Deserialize<StreamResponse>(line["data:".Length..], A2AJsonUtilities.DefaultOptions)!;
                return streamed.Task?.Id ?? streamed.StatusUpdate?.TaskId
                    ?? throw new InvalidOperationException("The first streamed event did not identify a task.");
            }
        }

        throw new InvalidOperationException("The stream ended before any event was received.");
    }

    private static async Task<T?> DeserializeAsync<T>(HttpResponseMessage response, CancellationToken cancellationToken) =>
        JsonSerializer.Deserialize<T>(await response.Content.ReadAsStringAsync(cancellationToken), A2AJsonUtilities.DefaultOptions);

    private static async Task<HttpResponseMessage> SendAsync(
        HttpClient client, HttpMethod method, string principal, string path, object? body, CancellationToken cancellationToken)
    {
        using HttpRequestMessage request = CreateRequest(method, principal, path, body);
        return await client.SendAsync(request, cancellationToken);
    }

    private static HttpRequestMessage CreateRequest(HttpMethod method, string principal, string path, object? body)
    {
        var request = new HttpRequestMessage(method, new Uri(path, UriKind.Relative));
        request.Headers.Add(UserHeader, principal);
        if (body is not null)
        {
            request.Content = new StringContent(JsonSerializer.Serialize(body, A2AJsonUtilities.DefaultOptions), Encoding.UTF8, "application/json");
        }

        return request;
    }

    private async Task<HttpClient> CreateTestServerAsync(CancellationToken cancellationToken)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        builder.Services.AddKeyedSingleton<IChatClient>(
            "chat-client", (sp, _) => new GatedChatClient(sp.GetRequiredService<IHttpContextAccessor>()));
        builder.AddAIAgent(AgentName, "You are a helpful assistant.", chatClientServiceKey: "chat-client")
            .WithSessionStore(this._sessionStore)
            .AddA2AServer(options => options.AgentRunMode = AgentRunMode.ReturnTask);

        // The provider resolves the caller from the live request only, like claims-based isolation does.
        builder.Services.AddHttpContextAccessor();
        builder.Services.AddSingleton<AgentIsolationKeyProvider>(
            sp => new HeaderAgentIsolationKeyProvider(sp.GetRequiredService<IHttpContextAccessor>()));

        this._app = builder.Build();
        this._app.MapA2AHttpJson(AgentName, "/a2a");
        await this._app.StartAsync(cancellationToken);

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        this._httpClient = testServer.CreateClient();
        return this._httpClient;
    }

    public async ValueTask DisposeAsync()
    {
        this._httpClient?.Dispose();

        if (this._app is not null)
        {
            await this._app.DisposeAsync();
        }
    }

    private sealed class HeaderAgentIsolationKeyProvider(IHttpContextAccessor httpContextAccessor) : AgentIsolationKeyProvider
    {
        public override ValueTask<string?> GetIsolationKeyAsync(CancellationToken cancellationToken = default)
        {
            string? key = httpContextAccessor.HttpContext?.Request.Headers[UserHeader].ToString();
            return new ValueTask<string?>(string.IsNullOrEmpty(key) ? null : key);
        }
    }

    /// <summary>
    /// A chat client that holds its reply until the request that started the run has ended,
    /// so the run continues only once the isolation provider can no longer resolve the caller.
    /// </summary>
    private sealed class GatedChatClient(IHttpContextAccessor httpContextAccessor) : IChatClient
    {
        public async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            await this.WaitForRequestToEndAsync(cancellationToken);
            return new ChatResponse(new ChatMessage(ChatRole.Assistant, AgentReply));
        }

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await this.WaitForRequestToEndAsync(cancellationToken);
            yield return new ChatResponseUpdate(ChatRole.Assistant, AgentReply) { MessageId = "reply" };
        }

        public object? GetService(Type serviceType, object? serviceKey = null) =>
            serviceType.IsInstanceOfType(this) ? this : null;

        public void Dispose() { }

        // The run's async flow shares the request's HttpContext holder, which ASP.NET Core clears when the request ends.
        private async Task WaitForRequestToEndAsync(CancellationToken cancellationToken)
        {
            while (httpContextAccessor.HttpContext is not null)
            {
                await Task.Delay(TimeSpan.FromMilliseconds(10), cancellationToken);
            }
        }
    }

    /// <summary>
    /// A session store that records the first saved key, after the isolation layer that wraps it has scoped the key.
    /// </summary>
    private sealed class RecordingSessionStore : AgentSessionStore
    {
        private readonly InMemoryAgentSessionStore _inner = new();

        public TaskCompletionSource<AgentSessionStoreKey> Saved { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public override ValueTask<AgentSession?> GetSessionAsync(AIAgent agent, AgentSessionStoreKey key, CancellationToken cancellationToken = default) =>
            this._inner.GetSessionAsync(agent, key, cancellationToken);

        public override async ValueTask SaveSessionAsync(AIAgent agent, AgentSessionStoreKey key, AgentSession session, CancellationToken cancellationToken = default)
        {
            await this._inner.SaveSessionAsync(agent, key, session, cancellationToken);
            this.Saved.TrySetResult(key);
        }

        public override ValueTask DeleteSessionAsync(AIAgent agent, AgentSessionStoreKey key, CancellationToken cancellationToken = default) =>
            this._inner.DeleteSessionAsync(agent, key, cancellationToken);
    }
}
