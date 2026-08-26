// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

[CollectionDefinition(CollectionName, DisableParallelization = true)]
public sealed class FoundryStateStoreLocalFallbackCollectionDefinition
{
    public const string CollectionName = "Foundry state-store local fallback";
}

[Collection(FoundryStateStoreLocalFallbackCollectionDefinition.CollectionName)]
public sealed class FoundryStateStoreLocalFallbackTests
{
    [Fact]
    public async Task StoresWithoutCredential_RoundTripThroughTheSdkLocalFallbackAsync()
    {
        // Arrange
        string root = Path.Combine(Path.GetTempPath(), $"foundry-state-store-local-{Guid.NewGuid():N}");
        string? previousStateRoot = Environment.GetEnvironmentVariable("AGENTSERVER_STATE_ROOT");
        string? previousHostingEnvironment = Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT");

        try
        {
            Environment.SetEnvironmentVariable("AGENTSERVER_STATE_ROOT", root);
            Environment.SetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT", null);

            var agent = new TestAgent();
            var sessionStore = new FoundryAgentSessionStore();
            var checkpointStore = new FoundryJsonCheckpointStore();

            // Act
            await sessionStore.SaveSessionAsync(agent, "conversation-1", new TestSession(), userId: "user-1");
            AgentSession? session = await sessionStore.GetSessionAsync(agent, "conversation-1", userId: "user-1");

            using JsonDocument document = JsonDocument.Parse("""{"step":1}""");
            CheckpointInfo checkpointInfo = await checkpointStore.CreateCheckpointAsync(
                "workflow-session-1",
                document.RootElement.Clone());
            JsonElement checkpoint = await checkpointStore.RetrieveCheckpointAsync(
                "workflow-session-1",
                checkpointInfo);

            // Assert
            Assert.NotNull(session);
            Assert.Equal("saved", agent.LastDeserialized?.GetProperty("session").GetString());
            Assert.Equal(1, checkpoint.GetProperty("step").GetInt32());
            Assert.True(Directory.Exists(Path.Combine(root, "state_stores")));
        }
        finally
        {
            Environment.SetEnvironmentVariable("AGENTSERVER_STATE_ROOT", previousStateRoot);
            Environment.SetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT", previousHostingEnvironment);

            if (Directory.Exists(root))
            {
                Directory.Delete(root, recursive: true);
            }
        }
    }

    private sealed class TestSession : AgentSession;

    private sealed class TestAgent : AIAgent
    {
        public override string? Name => "local-fallback-agent";

        public JsonElement? LastDeserialized { get; private set; }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new TestSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
        {
            using JsonDocument document = JsonDocument.Parse("""{"session":"saved"}""");
            return new(document.RootElement.Clone());
        }

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
        {
            this.LastDeserialized = serializedState.Clone();
            return new(new TestSession());
        }

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();
    }
}
