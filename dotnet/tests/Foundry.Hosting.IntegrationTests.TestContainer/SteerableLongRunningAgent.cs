// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Foundry.Hosting.IntegrationTests.TestContainer;

internal sealed class SteerableLongRunningAgent : AIAgent
{
    private int _activeRuns;
    private int _maxConcurrentRuns;

    public override string? Name => "steerable-long-running-agent";

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session,
        AgentRunOptions? options,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var steeringSession = session as SteeringSession
            ?? throw new InvalidOperationException("The steering agent requires a SteeringSession.");
        int activeRuns = Interlocked.Increment(ref this._activeRuns);
        UpdateMaximum(ref this._maxConcurrentRuns, activeRuns);

        try
        {
            int sessionTurn = ++steeringSession.Turn;
            string input = string.Join(
                "\n",
                messages.Select(message => message.Text).Where(text => text is not null));
            string[] parts = input.Split(':', 2, StringSplitOptions.TrimEntries);
            if (parts.Length != 2 || string.IsNullOrWhiteSpace(parts[1]))
            {
                throw new InvalidOperationException("Expected '<mode>:<token>'.");
            }

            string mode = parts[0];
            string token = parts[1];
            if (string.Equals(mode, "first", StringComparison.Ordinal))
            {
                yield return NewUpdate(
                    $"FIRST-STARTED:{token}:SESSION-TURN-{sessionTurn}");

                int delaySeconds = GetLongRunningDelaySeconds();
                await Task.Delay(
                    TimeSpan.FromSeconds(delaySeconds),
                    cancellationToken).ConfigureAwait(false);

                yield return NewUpdate(
                    $"FIRST-NATURAL-COMPLETE:{token}:SESSION-TURN-{sessionTurn}");
                yield break;
            }

            if (string.Equals(mode, "steer", StringComparison.Ordinal))
            {
                yield return NewUpdate(
                    $"STEERED-COMPLETE:{token}:SESSION-TURN-{sessionTurn}:" +
                    $"MAX-CONCURRENCY-{this.MaxConcurrentRuns}");
                yield break;
            }

            throw new InvalidOperationException(
                $"Unknown steerable long-running mode '{mode}'.");
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
        new(new SteeringSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
        AgentSession session,
        JsonSerializerOptions? jsonSerializerOptions,
        CancellationToken cancellationToken = default)
    {
        var steeringSession = session as SteeringSession
            ?? throw new InvalidOperationException("The steering agent requires a SteeringSession.");
        return new(JsonSerializer.SerializeToElement(
            new SerializedSession(steeringSession.Turn),
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
                "Could not deserialize the steering session.");
        return new(new SteeringSession { Turn = state.Turn });
    }

    private int MaxConcurrentRuns => Volatile.Read(ref this._maxConcurrentRuns);

    private static AgentResponseUpdate NewUpdate(string text) =>
        new()
        {
            MessageId = Guid.NewGuid().ToString("N"),
            Contents = [new TextContent(text)],
        };

    private static int GetLongRunningDelaySeconds()
    {
        const int DefaultDelaySeconds = 30;
        string? value = Environment.GetEnvironmentVariable(
            "IT_STEERING_LONG_RUNNING_DELAY_SECONDS");
        return int.TryParse(value, out int seconds) && seconds > 0
            ? seconds
            : DefaultDelaySeconds;
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

    private sealed class SteeringSession : AgentSession
    {
        public int Turn { get; set; }
    }

    private sealed record SerializedSession(int Turn);
}
