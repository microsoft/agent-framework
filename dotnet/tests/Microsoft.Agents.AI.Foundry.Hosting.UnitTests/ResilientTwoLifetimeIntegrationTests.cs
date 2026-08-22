// Copyright (c) Microsoft. All rights reserved.

using System;
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
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

[Collection(FoundryStateStoreLocalFallbackCollectionDefinition.CollectionName)]
public sealed class ResilientTwoLifetimeIntegrationTests
{
    [Fact]
    public async Task StoppedHost_RecoversMafAgentFromPersistedSessionAsync()
    {
        // Arrange
        string stateRoot = Path.Combine(
            Path.GetTempPath(),
            $"maf-recovery-{Guid.NewGuid():N}");
        string? previousStateRoot =
            Environment.GetEnvironmentVariable("AGENTSERVER_STATE_ROOT");
        string? previousHostingEnvironment =
            Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT");
        var coordinator = new RecoveryCoordinator();

        try
        {
            Environment.SetEnvironmentVariable("AGENTSERVER_STATE_ROOT", stateRoot);
            Environment.SetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT", null);

            string conversationId = $"conv_{Guid.NewGuid():N}";
            string responseId;

            WebApplication firstHost = await StartServerAsync(
                new ResumableAgent(coordinator),
                new PhaseObservingSessionStore(
                    new FoundryAgentSessionStore(),
                    coordinator));
            try
            {
                using HttpClient firstClient = GetClient(firstHost);
                responseId = await StartBackgroundResponseAsync(
                    firstClient,
                    conversationId);
                try
                {
                    await coordinator.PhasePersisted.Task.WaitAsync(
                        TimeSpan.FromSeconds(15));
                }
                catch (TimeoutException ex)
                {
                    throw new TimeoutException(
                        "Phase 1 was not observed in the persisted session. States: " +
                        string.Join(Environment.NewLine, coordinator.SerializedStates),
                        ex);
                }

                using CancellationTokenSource stopTimeout =
                    new(TimeSpan.FromSeconds(15));
                await firstHost.StopAsync(stopTimeout.Token);
            }
            finally
            {
                await firstHost.DisposeAsync();
            }

            // Act
            await using WebApplication secondHost = await StartServerAsync(
                new ResumableAgent(coordinator),
                new FoundryAgentSessionStore());
            using HttpClient secondClient = GetClient(secondHost);
            JsonElement completed = await WaitForTerminalAsync(
                secondClient,
                responseId,
                TimeSpan.FromSeconds(20));

            // Assert
            Assert.Equal("completed", completed.GetProperty("status").GetString());
            Assert.Contains(
                "RECOVERED-COMPLETE",
                GetOutputText(completed),
                StringComparison.Ordinal);
            Assert.Equal(1, coordinator.FreshRuns);
            Assert.Equal(1, coordinator.RecoveryRuns);
            Assert.Empty(coordinator.RecoveryMessages);
        }
        finally
        {
            Environment.SetEnvironmentVariable(
                "AGENTSERVER_STATE_ROOT",
                previousStateRoot);
            Environment.SetEnvironmentVariable(
                "FOUNDRY_HOSTING_ENVIRONMENT",
                previousHostingEnvironment);

            if (Directory.Exists(stateRoot))
            {
                try
                {
                    Directory.Delete(stateRoot, recursive: true);
                }
                catch (IOException)
                {
                }
            }
        }
    }

    [Fact]
    public async Task StoppedHost_RecoversWorkflowWithCompleteOrderedOutputAsync()
    {
        // Arrange
        string stateRoot = Path.Combine(
            Path.GetTempPath(),
            $"maf-workflow-recovery-{Guid.NewGuid():N}");
        string checkpointRoot = Path.Combine(stateRoot, "workflow-checkpoints");
        string? previousStateRoot =
            Environment.GetEnvironmentVariable("AGENTSERVER_STATE_ROOT");
        string? previousHostingEnvironment =
            Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT");
        var coordinator = new CountdownRecoveryCoordinator(target: 6, blockAt: 3);
        string sessionStoreName = $"agent-framework/sessions-{Guid.NewGuid():N}";

        try
        {
            Environment.SetEnvironmentVariable("AGENTSERVER_STATE_ROOT", stateRoot);
            Environment.SetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT", null);

            string conversationId = $"conv_{Guid.NewGuid():N}";
            string responseId;

            using (var checkpointStore = new FileSystemJsonCheckpointStore(
                Directory.CreateDirectory(checkpointRoot)))
            {
                WebApplication firstHost = await StartServerAsync(
                    BuildCountdownWorkflowAgent(coordinator, checkpointStore),
                    new FoundryAgentSessionStore(storeName: sessionStoreName));
                try
                {
                    using HttpClient firstClient = GetClient(firstHost);
                    responseId = await StartBackgroundResponseAsync(
                        firstClient,
                        conversationId,
                        agentName: "countdown-workflow",
                        input: "Count down from 6");
                    await coordinator.Blocked.Task.WaitAsync(TimeSpan.FromSeconds(15));
                    await WaitForResponseProgressAsync(
                        firstClient,
                        responseId,
                        ["6", "5", "4"],
                        minimumOutputItems: 12,
                        timeout: TimeSpan.FromSeconds(15));

                    using CancellationTokenSource stopTimeout =
                        new(TimeSpan.FromSeconds(15));
                    await firstHost.StopAsync(stopTimeout.Token);
                }
                finally
                {
                    await firstHost.DisposeAsync();
                }
            }

            JsonElement persisted = ReadPersistedResponse(stateRoot, responseId);
            Assert.Equal(["6", "5", "4"], GetOutputTexts(persisted));
            Assert.True(
                persisted.TryGetProperty("metadata", out JsonElement metadata)
                && metadata.TryGetProperty("_internal_metadata", out _),
                persisted.GetRawText());

            // Act
            using var recoveryCheckpointStore = new FileSystemJsonCheckpointStore(
                Directory.CreateDirectory(checkpointRoot));
            await using WebApplication secondHost = await StartServerAsync(
                BuildCountdownWorkflowAgent(coordinator, recoveryCheckpointStore),
                new FoundryAgentSessionStore(storeName: sessionStoreName));
            using HttpClient secondClient = GetClient(secondHost);
            JsonElement completed = await WaitForTerminalAsync(
                secondClient,
                responseId,
                TimeSpan.FromSeconds(20));

            // Assert
            Assert.Equal("completed", completed.GetProperty("status").GetString());
            Assert.Equal(
                ["6", "5", "4", "3", "2", "1", "Countdown complete."],
                GetOutputTexts(completed));
        }
        finally
        {
            Environment.SetEnvironmentVariable(
                "AGENTSERVER_STATE_ROOT",
                previousStateRoot);
            Environment.SetEnvironmentVariable(
                "FOUNDRY_HOSTING_ENVIRONMENT",
                previousHostingEnvironment);

            if (Directory.Exists(stateRoot))
            {
                try
                {
                    Directory.Delete(stateRoot, recursive: true);
                }
                catch (IOException)
                {
                }
            }
        }
    }

    private static async Task<WebApplication> StartServerAsync(
        AIAgent agent,
        AgentSessionStore sessionStore)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Services.AddFoundryResponses(
            agent,
            sessionStore,
            options => options.ResilientBackground = true);
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

    private static async Task<string> StartBackgroundResponseAsync(
        HttpClient client,
        string conversationId,
        string agentName = "resumable-agent",
        string input = "start durable work")
    {
        string body = JsonSerializer.Serialize(new
        {
            model = agentName,
            input,
            store = true,
            background = true,
            conversation = conversationId,
        });
        using HttpResponseMessage response = await client.PostAsync(
            new Uri("/responses", UriKind.Relative),
            new StringContent(body, Encoding.UTF8, "application/json"));
        response.EnsureSuccessStatusCode();

        using JsonDocument document = JsonDocument.Parse(
            await response.Content.ReadAsStringAsync());
        return document.RootElement.GetProperty("id").GetString()
            ?? throw new InvalidOperationException(
                "The background response did not contain an id.");
    }

    private static async Task<JsonElement> WaitForTerminalAsync(
        HttpClient client,
        string responseId,
        TimeSpan timeout)
    {
        var deadline = DateTimeOffset.UtcNow + timeout;
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
                JsonElement root = document.RootElement;
                string? status = root.GetProperty("status").GetString();
                if (status == "completed")
                {
                    return root.Clone();
                }

                if (status is "failed" or "cancelled" or "incomplete")
                {
                    throw new InvalidOperationException(
                        $"Response '{responseId}' terminated with status '{status}': {body}");
                }
            }

            await Task.Delay(TimeSpan.FromMilliseconds(50));
        }

        throw new TimeoutException(
            $"Response '{responseId}' did not complete. Last response: {last}");
    }

    private static async Task WaitForResponseProgressAsync(
        HttpClient client,
        string responseId,
        IReadOnlyList<string> expected,
        int minimumOutputItems,
        TimeSpan timeout)
    {
        var deadline = DateTimeOffset.UtcNow + timeout;
        List<string> last = [];
        while (DateTimeOffset.UtcNow < deadline)
        {
            using HttpResponseMessage response = await client.GetAsync(
                new Uri($"/responses/{responseId}", UriKind.Relative));
            if (response.StatusCode == HttpStatusCode.OK)
            {
                using JsonDocument document = JsonDocument.Parse(
                    await response.Content.ReadAsStringAsync());
                JsonElement root = document.RootElement;
                last = GetOutputTexts(root);
                if (last.Count == expected.Count
                    && last.SequenceEqual(expected)
                    && root.GetProperty("output").GetArrayLength() >= minimumOutputItems)
                {
                    return;
                }
            }

            await Task.Delay(TimeSpan.FromMilliseconds(25));
        }

        throw new TimeoutException(
            $"Response '{responseId}' did not reach the expected checkpointed output. " +
            $"Expected: {string.Join(", ", expected)}. Last: {string.Join(", ", last)}.");
    }

    private static JsonElement ReadPersistedResponse(
        string stateRoot,
        string responseId)
    {
        string path = Path.Combine(
            stateRoot,
            "responses",
            "envelopes",
            $"{responseId}.json");
        using JsonDocument document = JsonDocument.Parse(File.ReadAllBytes(path));
        return document.RootElement.GetProperty("envelope").Clone();
    }

    private static string GetOutputText(JsonElement response)
    {
        StringBuilder text = new();
        foreach (JsonElement item in response.GetProperty("output").EnumerateArray())
        {
            if (!item.TryGetProperty("content", out JsonElement content))
            {
                continue;
            }

            foreach (JsonElement part in content.EnumerateArray())
            {
                if (part.TryGetProperty("text", out JsonElement value))
                {
                    text.Append(value.GetString());
                }
            }
        }

        return text.ToString();
    }

    private static List<string> GetOutputTexts(JsonElement response)
    {
        List<string> texts = [];
        foreach (JsonElement item in response.GetProperty("output").EnumerateArray())
        {
            if (!item.TryGetProperty("content", out JsonElement content))
            {
                continue;
            }

            foreach (JsonElement part in content.EnumerateArray())
            {
                if (part.TryGetProperty("text", out JsonElement value)
                    && value.GetString() is { } text)
                {
                    texts.Add(text);
                }
            }
        }

        return texts;
    }

    private static AIAgent BuildCountdownWorkflowAgent(
        CountdownRecoveryCoordinator coordinator,
        FileSystemJsonCheckpointStore checkpointStore)
    {
        var start = new CountdownStartExecutor(coordinator.Target);
        var countdown = new CountdownExecutor(coordinator);
        var complete = new CountdownCompleteExecutor();
        Workflow workflow = new WorkflowBuilder(start)
            .AddEdge(start, countdown)
            .AddEdge(countdown, countdown)
            .AddEdge(countdown, complete)
            .WithOutputFrom(countdown, complete)
            .Build();

        return workflow.AsAIAgent(
            id: "countdown-workflow",
            name: "countdown-workflow",
            executionEnvironment: InProcessExecution.OffThread.WithCheckpointing(
                CheckpointManager.CreateJson(checkpointStore)),
            includeExceptionDetails: true,
            includeWorkflowOutputsInResponse: true);
    }

    [SendsMessage(typeof(int))]
    private sealed class CountdownStartExecutor(int target) : ChatProtocolExecutor(
        "start",
        new ChatProtocolExecutorOptions { AutoSendTurnToken = false })
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
            base.ConfigureProtocol(protocolBuilder).SendsMessage<int>();

        protected override ValueTask TakeTurnAsync(
            List<ChatMessage> messages,
            IWorkflowContext context,
            bool? emitEvents,
            CancellationToken cancellationToken = default) =>
            context.SendMessageAsync(target, cancellationToken: cancellationToken);
    }

    [SendsMessage(typeof(int))]
    [SendsMessage(typeof(string))]
    [YieldsOutput(typeof(string))]
    private sealed class CountdownExecutor(CountdownRecoveryCoordinator coordinator) : Executor<int>("countdown")
    {
        public override async ValueTask HandleAsync(
            int message,
            IWorkflowContext context,
            CancellationToken cancellationToken = default)
        {
            if (message <= 0)
            {
                await context.SendMessageAsync(
                    "Countdown complete.",
                    targetId: "complete",
                    cancellationToken: cancellationToken);
                return;
            }

            if (coordinator.ShouldBlock(message))
            {
                coordinator.Blocked.TrySetResult();
                await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            }

            await context.YieldOutputAsync(message.ToString(), cancellationToken);
            await context.SendMessageAsync(
                message - 1,
                targetId: "countdown",
                cancellationToken: cancellationToken);
        }
    }

    [YieldsOutput(typeof(string))]
    private sealed class CountdownCompleteExecutor() : Executor<string>("complete")
    {
        public override ValueTask HandleAsync(
            string message,
            IWorkflowContext context,
            CancellationToken cancellationToken = default) =>
            context.YieldOutputAsync(message, cancellationToken);
    }

    private sealed class ResumableAgent(RecoveryCoordinator coordinator) : AIAgent
    {
        protected override string? IdCore => "resumable-agent";

        public override string? Name => "resumable-agent";

        protected override async IAsyncEnumerable<AgentResponseUpdate>
            RunCoreStreamingAsync(
                IEnumerable<ChatMessage> messages,
                AgentSession? session,
                AgentRunOptions? options,
                [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            var resumableSession = session as ResumableSession
                ?? throw new InvalidOperationException(
                    "The resumable agent requires a ResumableSession.");
            string[] input = messages
                .Select(message => message.Text)
                .Where(text => text is not null)
                .ToArray()!;

            if (resumableSession.Phase == 0)
            {
                Interlocked.Increment(ref coordinator.FreshRuns);
                resumableSession.Phase = 1;
                yield return NewUpdate("PHASE-1-COMPLETE");
                yield return NewUpdate("PHASE-2-STARTED");
                await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
                yield break;
            }

            Interlocked.Increment(ref coordinator.RecoveryRuns);
            coordinator.RecoveryMessages = input;
            resumableSession.Phase = 2;
            yield return NewUpdate("RECOVERED-COMPLETE");
            await Task.CompletedTask;
        }

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            new(new ResumableSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default)
        {
            var resumableSession = session as ResumableSession
                ?? throw new InvalidOperationException(
                    "The resumable agent requires a ResumableSession.");
            return new(JsonSerializer.SerializeToElement(
                new SerializedSession(resumableSession.Phase),
                jsonSerializerOptions));
        }

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default)
        {
            SerializedSession state = serializedState.Deserialize<SerializedSession>(
                jsonSerializerOptions)
                ?? throw new InvalidOperationException(
                    "Could not deserialize the resumable session.");
            return new(new ResumableSession { Phase = state.Phase });
        }

        private static AgentResponseUpdate NewUpdate(string text) =>
            new()
            {
                MessageId = Guid.NewGuid().ToString("N"),
                Contents = [new TextContent(text)],
            };

        private sealed class ResumableSession : AgentSession
        {
            public int Phase { get; set; }
        }

        private sealed record SerializedSession(int Phase);
    }

    private sealed class PhaseObservingSessionStore(
        AgentSessionStore inner,
        RecoveryCoordinator coordinator) : AgentSessionStore
    {
        public override async ValueTask SaveSessionAsync(
            AIAgent agent,
            string conversationId,
            AgentSession session,
            string? userId,
            CancellationToken cancellationToken = default)
        {
            JsonElement state = await agent.SerializeSessionAsync(
                session,
                cancellationToken: cancellationToken);
            coordinator.SerializedStates.Add(state.GetRawText());
            await inner.SaveSessionAsync(
                agent,
                conversationId,
                session,
                userId,
                cancellationToken);

            JsonProperty? phaseProperty = state
                .EnumerateObject()
                .FirstOrDefault(property => string.Equals(
                    property.Name,
                    "phase",
                    StringComparison.OrdinalIgnoreCase));
            if (phaseProperty is { Value.ValueKind: JsonValueKind.Number }
                && phaseProperty.Value.Value.GetInt32() == 1)
            {
                coordinator.PhasePersisted.TrySetResult();
            }
        }

        public override ValueTask<AgentSession?> GetSessionAsync(
            AIAgent agent,
            string conversationId,
            string? userId,
            CancellationToken cancellationToken = default) =>
            inner.GetSessionAsync(
                agent,
                conversationId,
                userId,
                cancellationToken);
    }

    private sealed class RecoveryCoordinator
    {
        public int FreshRuns;
        public int RecoveryRuns;

        public string[] RecoveryMessages { get; set; } = [];

        public List<string> SerializedStates { get; } = [];

        public TaskCompletionSource PhasePersisted { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
    }

    private sealed class CountdownRecoveryCoordinator(int target, int blockAt)
    {
        private int _blocked;

        public int Target { get; } = target;

        public TaskCompletionSource Blocked { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public bool ShouldBlock(int value) =>
            value == blockAt && Interlocked.CompareExchange(ref this._blocked, 1, 0) == 0;
    }
}
