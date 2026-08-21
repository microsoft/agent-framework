// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using AGUI.Abstractions;
using AGUI.Client;
using Azure.Storage.Blobs;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.AzureStorage.Tests;

internal sealed class FakeTestAgentHost : IAsyncDisposable
{
    private const string AgentName = "azure-blob-session-agent";

    private readonly WebApplication _app;
    private readonly HttpClient _client;

    private FakeTestAgentHost(WebApplication app, HttpClient client)
    {
        this._app = app;
        this._client = client;
    }

    public static async Task<FakeTestAgentHost> StartAsync(BlobContainerClient containerClient)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Services.AddAGUIServer();
        builder.Services
            .AddAIAgent(AgentName, (_, name) => new SessionCountingAgent(name))
            .WithAzureBlobSessionStore(containerClient, withIsolation: false);

        WebApplication app = builder.Build();
        app.MapAGUIServer(AgentName, "/agent");
        await app.StartAsync();

        TestServer server = app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer was not registered.");
        HttpClient client = server.CreateClient();
        client.BaseAddress = new Uri("http://localhost/agent");

        return new FakeTestAgentHost(app, client);
    }

    public async Task<FakeTestAgentRunResult> RunTwoTurnsAsync()
    {
        var chatClient = new AGUIChatClient(new(this._client, ""));
        AIAgent clientAgent = chatClient.AsAIAgent(
            instructions: null,
            name: "client-agent",
            description: "Client for the in-memory test agent host.",
            tools: []);
        AgentSession clientSession = await clientAgent.CreateSessionAsync();

        ChatMessage firstMessage = new(ChatRole.User, "first turn");
        List<AgentResponseUpdate> firstUpdates = [];
        await foreach (AgentResponseUpdate update in clientAgent.RunStreamingAsync(
            [firstMessage],
            clientSession,
            new AgentRunOptions(),
            CancellationToken.None))
        {
            firstUpdates.Add(update);
        }

        RunStartedEvent runStarted = firstUpdates
            .Select(update => update.AsChatResponseUpdate().RawRepresentation as RunStartedEvent)
            .First(evt => evt is not null)!;

        ChatMessage secondMessage = new(ChatRole.User, "second turn");
        var continuationOptions = new ChatClientAgentRunOptions
        {
            ChatOptions = new ChatOptions
            {
                RawRepresentationFactory = _ => new RunAgentInput
                {
                    ThreadId = runStarted.ThreadId,
                    ParentRunId = runStarted.RunId,
                    Messages = new[] { secondMessage }.AsAGUIMessages().ToList(),
                },
            },
        };

        List<AgentResponseUpdate> secondUpdates = [];
        await foreach (AgentResponseUpdate update in clientAgent.RunStreamingAsync(
            [secondMessage],
            clientSession,
            continuationOptions,
            CancellationToken.None))
        {
            secondUpdates.Add(update);
        }

        return new(
            firstUpdates.ToAgentResponse().Text,
            secondUpdates.ToAgentResponse().Text);
    }

    public async ValueTask DisposeAsync()
    {
        this._client.Dispose();
        await this._app.DisposeAsync();
    }

    internal sealed record FakeTestAgentRunResult(
        string FirstResponse,
        string SecondResponse);

    private sealed class SessionCountingAgent(string name) : AIAgent
    {
        protected override string? IdCore => name;

        public override string? Name => name;

        public override string? Description => "A deterministic agent that stores its turn count in the session.";

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new SessionCountingAgentSession());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
            => new(serializedState.Deserialize<SessionCountingAgentSession>(jsonSerializerOptions)!);

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
        {
            if (session is not SessionCountingAgentSession countingSession)
            {
                throw new InvalidOperationException(
                    $"The session type '{session.GetType().Name}' is not supported.");
            }

            return new(JsonSerializer.SerializeToElement(countingSession, jsonSerializerOptions));
        }

        protected override async Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            List<AgentResponseUpdate> updates = [];
            await foreach (AgentResponseUpdate update in this.RunStreamingAsync(
                messages,
                session,
                options,
                cancellationToken).ConfigureAwait(false))
            {
                updates.Add(update);
            }

            return updates.ToAgentResponse();
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            int turnCount = (session?.StateBag.GetValue<TurnCounter>("turnCounter")?.Count ?? 0) + 1;
            session?.StateBag.SetValue("turnCounter", new TurnCounter { Count = turnCount });

            yield return new AgentResponseUpdate
            {
                MessageId = Guid.NewGuid().ToString("N"),
                Role = ChatRole.Assistant,
                Contents = [new TextContent($"Turn {turnCount}: session persisted")],
            };

            await Task.Yield();
        }

        private sealed class TurnCounter
        {
            public int Count { get; set; }
        }

        private sealed class SessionCountingAgentSession : AgentSession
        {
            public SessionCountingAgentSession()
            {
            }

            [JsonConstructor]
            public SessionCountingAgentSession(AgentSessionStateBag stateBag)
                : base(stateBag)
            {
            }
        }
    }
}
