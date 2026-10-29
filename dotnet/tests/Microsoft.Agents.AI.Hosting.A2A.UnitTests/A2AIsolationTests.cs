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

    private readonly GatedChatClient _chatClient = new();
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

        // Act: the request returns while the agent is still running, then the run finishes.
        using HttpResponseMessage response = await SendAsync(client, HttpMethod.Post, Alice, "/a2a/message:send", request, cts.Token);
        response.EnsureSuccessStatusCode();
        SendMessageResponse sendResponse = (await DeserializeAsync<SendMessageResponse>(response, cts.Token))!;
        string taskId = sendResponse.Task!.Id;

        this._chatClient.Release();

        // Assert
        AgentTask task = await WaitForTerminalTaskAsync(client, Alice, taskId, cts.Token);
        Assert.Equal(TaskState.Completed, task.Status.State);
        Assert.Equal(AgentReply, Assert.Single(Assert.Single(task.Artifacts!).Parts!).Text);

        using HttpResponseMessage bobResponse = await SendAsync(client, HttpMethod.Get, Bob, $"/a2a/tasks/{taskId}", body: null, cts.Token);
        Assert.Equal(HttpStatusCode.NotFound, bobResponse.StatusCode);
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

        // Act: read the first event, disconnect, then let the run finish.
        string taskId;
        using (var httpRequest = CreateRequest(HttpMethod.Post, Alice, "/a2a/message:stream", request))
        using (HttpResponseMessage response = await client.SendAsync(httpRequest, HttpCompletionOption.ResponseHeadersRead, cts.Token))
        {
            response.EnsureSuccessStatusCode();
            taskId = await ReadFirstStreamedTaskIdAsync(response, cts.Token);
        }

        this._chatClient.Release();

        // Assert
        AgentTask task = await WaitForTerminalTaskAsync(client, Alice, taskId, cts.Token);
        Assert.Equal(TaskState.Completed, task.Status.State);
        Assert.Equal(AgentReply, Assert.Single(Assert.Single(task.Artifacts!).Parts!).Text);
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

        builder.Services.AddKeyedSingleton<IChatClient>("chat-client", this._chatClient);
        builder.AddAIAgent(AgentName, "You are a helpful assistant.", chatClientServiceKey: "chat-client")
            .WithInMemorySessionStore()
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
        this._chatClient.Release();
        this._httpClient?.Dispose();
        this._chatClient.Dispose();

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
    /// A chat client that holds its reply until released, so the run outlives the request that started it.
    /// </summary>
    private sealed class GatedChatClient : IChatClient
    {
        private readonly TaskCompletionSource _gate = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public void Release() => this._gate.TrySetResult();

        public async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            await this._gate.Task.WaitAsync(cancellationToken);
            return new ChatResponse(new ChatMessage(ChatRole.Assistant, AgentReply));
        }

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await this._gate.Task.WaitAsync(cancellationToken);
            yield return new ChatResponseUpdate(ChatRole.Assistant, AgentReply) { MessageId = "reply" };
        }

        public object? GetService(Type serviceType, object? serviceKey = null) =>
            serviceType.IsInstanceOfType(this) ? this : null;

        public void Dispose() { }
    }
}
