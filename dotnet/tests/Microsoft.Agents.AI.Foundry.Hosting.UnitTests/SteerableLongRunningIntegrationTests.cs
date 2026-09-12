// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

[Collection(FoundryStateStoreLocalFallbackCollectionDefinition.CollectionName)]
public sealed class SteerableLongRunningIntegrationTests
{
    [Fact]
    public async Task ActiveMafTurn_QueuesSteeringThenRunsItOnTheSameSessionAsync()
    {
        // Arrange
        string stateRoot = Path.Combine(Path.GetTempPath(), $"maf-steering-{Guid.NewGuid():N}");
        string? previousStateRoot = Environment.GetEnvironmentVariable("AGENTSERVER_STATE_ROOT");
        string? previousHostingEnvironment = Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT");
        var agent = new GatedSteeringAgent();

        try
        {
            Environment.SetEnvironmentVariable("AGENTSERVER_STATE_ROOT", stateRoot);
            Environment.SetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT", null);

            await using WebApplication app = await StartServerAsync(agent);
            using HttpClient client = GetClient(app);
            string conversationId = $"conv_{Guid.NewGuid():N}";

            using HttpResponseMessage first = await PostTurnAsync(client, conversationId, "first instruction");
            using JsonDocument firstBody = await ParseAsync(first);
            string firstResponseId = firstBody.RootElement.GetProperty("id").GetString()!;
            await agent.FirstTurnEntered.Task.WaitAsync(TimeSpan.FromSeconds(10));

            // Act
            using HttpResponseMessage second = await PostTurnAsync(client, conversationId, "steering instruction");
            using JsonDocument secondBody = await ParseAsync(second);
            string secondResponseId = secondBody.RootElement.GetProperty("id").GetString()!;

            // Assert: AgentServer queued the second input rather than invoking MAF concurrently.
            Assert.Equal(HttpStatusCode.OK, second.StatusCode);
            Assert.Equal("queued", secondBody.RootElement.GetProperty("status").GetString());
            Assert.Equal(1, agent.RunCount);
            Assert.Equal(1, agent.MaxConcurrentRuns);

            agent.ReleaseFirstTurn.TrySetResult();
            await agent.SecondTurnEntered.Task.WaitAsync(TimeSpan.FromSeconds(10));
            await WaitForTerminalAsync(client, firstResponseId);
            await WaitForTerminalAsync(client, secondResponseId);

            Assert.Equal(2, agent.RunCount);
            Assert.Equal(1, agent.MaxConcurrentRuns);
            Assert.Collection(
                agent.ObservedTurns,
                firstTurn =>
                {
                    Assert.Equal(1, firstTurn.SessionTurn);
                    Assert.Contains("first instruction", firstTurn.Input, StringComparison.Ordinal);
                },
                secondTurn =>
                {
                    Assert.Equal(2, secondTurn.SessionTurn);
                    Assert.Contains("steering instruction", secondTurn.Input, StringComparison.Ordinal);
                });
        }
        finally
        {
            agent.ReleaseFirstTurn.TrySetResult();
            Environment.SetEnvironmentVariable("AGENTSERVER_STATE_ROOT", previousStateRoot);
            Environment.SetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT", previousHostingEnvironment);

            if (Directory.Exists(stateRoot))
            {
                Directory.Delete(stateRoot, recursive: true);
            }
        }
    }

    private static async Task<WebApplication> StartServerAsync(AIAgent agent)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Services.AddFoundryResponses(
            agent,
            new InMemoryAgentSessionStore(),
            options =>
            {
                options.ResilientBackground = true;
                options.SteerableConversations = true;
            });
        builder.Services.AddSingleton<HostedSessionIsolationKeyProvider>(
            new FakeHostedSessionIsolationKeyProvider());
        builder.Services.AddLogging();

        WebApplication app = builder.Build();
        app.MapFoundryResponses();
        await app.StartAsync();
        return app;
    }

    private static HttpClient GetClient(WebApplication app) =>
        (app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found."))
        .CreateClient();

    private static Task<HttpResponseMessage> PostTurnAsync(
        HttpClient client,
        string conversationId,
        string input)
    {
        string body = JsonSerializer.Serialize(new
        {
            model = "steering-probe",
            input,
            store = true,
            background = true,
            conversation = conversationId,
        });
        return client.PostAsync(
            new Uri("/responses", UriKind.Relative),
            new StringContent(body, Encoding.UTF8, "application/json"));
    }

    private static async Task<JsonDocument> ParseAsync(HttpResponseMessage response) =>
        JsonDocument.Parse(await response.Content.ReadAsStringAsync());

    private static async Task WaitForTerminalAsync(HttpClient client, string responseId)
    {
        var deadline = DateTimeOffset.UtcNow.AddSeconds(15);
        string last = "(none)";
        while (DateTimeOffset.UtcNow < deadline)
        {
            using HttpResponseMessage response = await client.GetAsync(
                new Uri($"/responses/{responseId}", UriKind.Relative));
            string body = await response.Content.ReadAsStringAsync();
            last = $"{(int)response.StatusCode} {body}";
            if (response.StatusCode == HttpStatusCode.OK)
            {
                using JsonDocument document = JsonDocument.Parse(body);
                string? status = document.RootElement.GetProperty("status").GetString();
                if (status == "completed")
                {
                    return;
                }

                if (status is "failed" or "cancelled" or "incomplete")
                {
                    throw new InvalidOperationException(
                        $"Response '{responseId}' terminated with status '{status}'.");
                }
            }

            await Task.Delay(TimeSpan.FromMilliseconds(25));
        }

        throw new TimeoutException(
            $"Response '{responseId}' did not complete. Last response: {last}");
    }

    private sealed class GatedSteeringAgent : AIAgent
    {
        private readonly ConcurrentQueue<ObservedTurn> _observedTurns = new();
        private int _activeRuns;
        private int _maxConcurrentRuns;
        private int _runCount;

        public TaskCompletionSource FirstTurnEntered { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TaskCompletionSource ReleaseFirstTurn { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TaskCompletionSource SecondTurnEntered { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public int RunCount => Volatile.Read(ref this._runCount);

        public int MaxConcurrentRuns => Volatile.Read(ref this._maxConcurrentRuns);

        public IReadOnlyList<ObservedTurn> ObservedTurns => this._observedTurns.ToArray();

        public override string? Name => "steering-probe";

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            var probeSession = Assert.IsType<ProbeSession>(session);
            int activeRuns = Interlocked.Increment(ref this._activeRuns);
            UpdateMaximum(ref this._maxConcurrentRuns, activeRuns);

            try
            {
                int run = Interlocked.Increment(ref this._runCount);
                int sessionTurn = ++probeSession.Turn;
                string input = string.Join(
                    "\n",
                    messages.Select(message => message.Text).Where(text => text is not null));
                this._observedTurns.Enqueue(new(sessionTurn, input));

                if (run == 1)
                {
                    this.FirstTurnEntered.TrySetResult();
                    await this.ReleaseFirstTurn.Task.WaitAsync(cancellationToken);
                }
                else
                {
                    this.SecondTurnEntered.TrySetResult();
                }

                yield return new AgentResponseUpdate
                {
                    MessageId = $"msg_{run}",
                    Contents = [new TextContent($"TURN-{sessionTurn}-COMPLETE")],
                };
            }
            finally
            {
                Interlocked.Decrement(ref this._activeRuns);
            }
        }

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            new(new ProbeSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default)
        {
            var probeSession = Assert.IsType<ProbeSession>(session);
            return new(JsonSerializer.SerializeToElement(
                new SerializedSession(probeSession.Turn),
                jsonSerializerOptions));
        }

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default)
        {
            SerializedSession state = serializedState.Deserialize<SerializedSession>(
                jsonSerializerOptions)
                ?? throw new InvalidOperationException("Could not deserialize the steering session.");
            return new(new ProbeSession { Turn = state.Turn });
        }

        private static void UpdateMaximum(ref int maximum, int candidate)
        {
            int current;
            do
            {
                current = Volatile.Read(ref maximum);
                if (candidate <= current)
                {
                    return;
                }
            }
            while (Interlocked.CompareExchange(ref maximum, candidate, current) != current);
        }

        private sealed class ProbeSession : AgentSession
        {
            public int Turn { get; set; }
        }

        private sealed record SerializedSession(int Turn);
    }

    private sealed record ObservedTurn(int SessionTurn, string Input);
}
