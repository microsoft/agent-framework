// Copyright (c) Microsoft. All rights reserved.

using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Foundry.Hosting.IntegrationTests.TestContainer;

internal static class ResilientWorkflowAgent
{
    // Agent Administration tracks the durable session, not individual process lifetimes.
    // Persist our own incarnation so recovery can prove that a different process continued the work.
    private static readonly string s_processIncarnation = Guid.NewGuid().ToString("N");

    public static AIAgent Create()
    {
        ResilientInputExecutor input = new();
        ResilientWorkExecutor work = new();
        ResilientOutputExecutor output = new();
        ResilientCountdownExecutor countdown = new();
        ResilientCountdownCrashExecutor countdownCrash = new();
        ResilientCountdownCompleteExecutor countdownComplete = new();

        return new WorkflowBuilder(input)
            .AddEdge(input, work)
            .AddEdge(input, countdown)
            .AddEdge(work, output)
            .AddEdge(countdown, countdown)
            .AddEdge(countdown, countdownCrash)
            .AddEdge(countdown, countdownComplete)
            .AddEdge(countdownCrash, countdown)
            .WithOutputFrom(output, countdown, countdownComplete)
            .Build()
            .AsAIAgent(
                name: "resilient-workflow-agent",
                includeExceptionDetails: true,
                includeWorkflowOutputsInResponse: true);
    }

    private sealed class ResilientInputExecutor()
        : ChatProtocolExecutor("resilient-input", new() { AutoSendTurnToken = false })
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
            base.ConfigureProtocol(protocolBuilder).SendsMessage<string>();

        protected override ValueTask TakeTurnAsync(
            List<ChatMessage> messages,
            IWorkflowContext context,
            bool? emitEvents,
            CancellationToken cancellationToken = default)
        {
            string request = messages.LastOrDefault()?.Text
                ?? throw new InvalidOperationException("The resilient workflow requires an input message.");
            string targetId = request.StartsWith("countdown:", StringComparison.Ordinal)
                ? "resilient-countdown"
                : "resilient-work";
            return context.SendMessageAsync(
                request,
                targetId: targetId,
                cancellationToken: cancellationToken);
        }
    }

    private sealed class ResilientWorkExecutor()
        : Executor<string, string>("resilient-work")
    {
        public override async ValueTask<string> HandleAsync(
            string message,
            IWorkflowContext context,
            CancellationToken cancellationToken = default)
        {
            string[] parts = message.Split(':', 2, StringSplitOptions.TrimEntries);
            if (parts.Length != 2 || string.IsNullOrWhiteSpace(parts[1]))
            {
                throw new InvalidOperationException("Expected '<mode>:<token>'.");
            }

            string mode = parts[0];
            string token = parts[1];

            if (string.Equals(mode, "long", StringComparison.Ordinal))
            {
                int delaySeconds = GetLongRunningDelaySeconds();
                await Task.Delay(TimeSpan.FromSeconds(delaySeconds), cancellationToken).ConfigureAwait(false);
                return $"LONG-RUN-COMPLETE:{token}";
            }

            if (string.Equals(mode, "crash", StringComparison.Ordinal))
            {
                if (TryCreateCrashMarker(token, out string crashedProcessIncarnation))
                {
                    await Task.Delay(
                        TimeSpan.FromSeconds(GetCrashDelaySeconds()),
                        cancellationToken).ConfigureAwait(false);
                    Console.Out.Flush();
                    Console.Error.Flush();
                    Environment.Exit(70);
                    throw new InvalidOperationException("Process termination did not stop execution.");
                }

                if (string.Equals(crashedProcessIncarnation, s_processIncarnation, StringComparison.Ordinal))
                {
                    throw new InvalidOperationException("The crash recovery stage resumed in the original process.");
                }

                return $"CRASH-RECOVERED:{token}:PROCESS-CHANGED";
            }

            throw new InvalidOperationException($"Unknown resilient workflow mode '{mode}'.");
        }

        private static int GetLongRunningDelaySeconds()
        {
            const int DefaultDelaySeconds = 20;
            string? value = Environment.GetEnvironmentVariable("IT_LONG_RUNNING_DELAY_SECONDS");
            return int.TryParse(value, out int seconds) && seconds > 0 ? seconds : DefaultDelaySeconds;
        }

        private static int GetCrashDelaySeconds()
        {
            const int DefaultDelaySeconds = 5;
            string? value = Environment.GetEnvironmentVariable(
                "IT_CRASH_DELAY_SECONDS");
            return int.TryParse(
                value,
                NumberStyles.None,
                CultureInfo.InvariantCulture,
                out int seconds)
                && seconds >= 0
                    ? seconds
                    : DefaultDelaySeconds;
        }
    }

    [SendsMessage(typeof(string))]
    [YieldsOutput(typeof(string))]
    private sealed class ResilientCountdownExecutor()
        : Executor<string>("resilient-countdown")
    {
        public override async ValueTask HandleAsync(
            string message,
            IWorkflowContext context,
            CancellationToken cancellationToken = default)
        {
            CountdownState state = CountdownState.Parse(message);
            if (state.Current <= 0)
            {
                await context.SendMessageAsync(
                    "Countdown complete.",
                    targetId: "resilient-countdown-complete",
                    cancellationToken: cancellationToken).ConfigureAwait(false);
                return;
            }

            await Task.Delay(
                TimeSpan.FromMilliseconds(GetCountdownDelayMilliseconds()),
                cancellationToken).ConfigureAwait(false);
            await context.YieldOutputAsync(
                state.Current.ToString(CultureInfo.InvariantCulture),
                cancellationToken).ConfigureAwait(false);

            CountdownState next = state with { Current = state.Current - 1 };
            string targetId = state.Current == state.CrashAtValue
                ? "resilient-countdown-crash"
                : "resilient-countdown";
            await context.SendMessageAsync(
                next.ToString(),
                targetId: targetId,
                cancellationToken: cancellationToken).ConfigureAwait(false);
        }

        private static int GetCountdownDelayMilliseconds()
        {
            const int DefaultDelayMilliseconds = 250;
            string? value = Environment.GetEnvironmentVariable(
                "IT_COUNTDOWN_DELAY_MILLISECONDS");
            return int.TryParse(
                value,
                NumberStyles.None,
                CultureInfo.InvariantCulture,
                out int milliseconds)
                && milliseconds >= 0
                    ? milliseconds
                    : DefaultDelayMilliseconds;
        }
    }

    [SendsMessage(typeof(string))]
    private sealed class ResilientCountdownCrashExecutor()
        : Executor<string>("resilient-countdown-crash")
    {
        public override async ValueTask HandleAsync(
            string message,
            IWorkflowContext context,
            CancellationToken cancellationToken = default)
        {
            CountdownState state = CountdownState.Parse(message);
            if (TryCreateCrashMarker(
                state.Token,
                out string crashedProcessIncarnation))
            {
                await Task.Delay(
                    TimeSpan.FromSeconds(GetCountdownCrashDelaySeconds()),
                    cancellationToken).ConfigureAwait(false);
                Console.Out.Flush();
                Console.Error.Flush();
                Environment.Exit(70);
                throw new InvalidOperationException(
                    "Process termination did not stop execution.");
            }

            if (string.Equals(
                crashedProcessIncarnation,
                s_processIncarnation,
                StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    "The countdown resumed in the original process.");
            }

            await context.SendMessageAsync(
                state.ToString(),
                targetId: "resilient-countdown",
                cancellationToken: cancellationToken).ConfigureAwait(false);
        }

        private static int GetCountdownCrashDelaySeconds()
        {
            const int DefaultDelaySeconds = 5;
            string? value = Environment.GetEnvironmentVariable(
                "IT_COUNTDOWN_CRASH_DELAY_SECONDS");
            return int.TryParse(
                value,
                NumberStyles.None,
                CultureInfo.InvariantCulture,
                out int seconds)
                && seconds >= 0
                    ? seconds
                    : DefaultDelaySeconds;
        }
    }

    [YieldsOutput(typeof(string))]
    private sealed class ResilientCountdownCompleteExecutor()
        : Executor<string>("resilient-countdown-complete")
    {
        public override ValueTask HandleAsync(
            string message,
            IWorkflowContext context,
            CancellationToken cancellationToken = default) =>
            context.YieldOutputAsync(message, cancellationToken);
    }

    [YieldsOutput(typeof(string))]
    private sealed class ResilientOutputExecutor()
        : Executor<string>("resilient-output")
    {
        public override async ValueTask HandleAsync(
            string message,
            IWorkflowContext context,
            CancellationToken cancellationToken = default)
        {
            await context.YieldOutputAsync(message, cancellationToken).ConfigureAwait(false);
        }
    }

    private static bool TryCreateCrashMarker(
        string token,
        out string crashedProcessIncarnation)
    {
        string home = Environment.GetEnvironmentVariable("HOME")
            ?? throw new InvalidOperationException("HOME is not set.");
        string markerDirectory = Path.Combine(
            home,
            ".foundry-hosting-it",
            "resilient-workflow");
        Directory.CreateDirectory(markerDirectory);

        string markerName =
            Convert.ToHexString(
                SHA256.HashData(Encoding.UTF8.GetBytes(token)))
            + ".crashed";
        string markerPath = Path.Combine(markerDirectory, markerName);

        try
        {
            using FileStream marker = new(
                markerPath,
                FileMode.CreateNew,
                FileAccess.Write,
                FileShare.None,
                bufferSize: 1,
                FileOptions.WriteThrough);
            byte[] incarnation = Encoding.UTF8.GetBytes(
                s_processIncarnation);
            marker.Write(incarnation);
            marker.Flush(flushToDisk: true);
            crashedProcessIncarnation = s_processIncarnation;
            return true;
        }
        catch (IOException) when (File.Exists(markerPath))
        {
            crashedProcessIncarnation =
                File.ReadAllText(markerPath, Encoding.UTF8).Trim();
            if (string.IsNullOrWhiteSpace(crashedProcessIncarnation))
            {
                throw new InvalidOperationException(
                    "The crash marker does not contain a process incarnation.");
            }

            return false;
        }
    }

    private sealed record CountdownState(
        int Current,
        int CrashAtValue,
        string Token)
    {
        private const string InitialPrefix = "countdown";
        private const string StatePrefix = "countdown-state";

        public static CountdownState Parse(string value)
        {
            string[] parts = value.Split(
                ':',
                4,
                StringSplitOptions.TrimEntries);
            if (parts.Length != 4
                || !int.TryParse(
                    parts[1],
                    NumberStyles.None,
                    CultureInfo.InvariantCulture,
                    out int first)
                || !int.TryParse(
                    parts[2],
                    NumberStyles.None,
                    CultureInfo.InvariantCulture,
                    out int second)
                || string.IsNullOrWhiteSpace(parts[3]))
            {
                throw new InvalidOperationException(
                    "Expected 'countdown:<target>:<crash-after-count>:<token>' " +
                    "or a valid countdown state.");
            }

            if (string.Equals(
                parts[0],
                InitialPrefix,
                StringComparison.Ordinal))
            {
                if (first < 2 || second < 1 || second >= first)
                {
                    throw new InvalidOperationException(
                        "Countdown target must be at least 2 and the crash count " +
                        "must be between 1 and target minus 1.");
                }

                return new(
                    Current: first,
                    CrashAtValue: first - second + 1,
                    Token: parts[3]);
            }

            if (string.Equals(
                parts[0],
                StatePrefix,
                StringComparison.Ordinal)
                && first >= 0
                && second > 0)
            {
                return new(
                    Current: first,
                    CrashAtValue: second,
                    Token: parts[3]);
            }

            throw new InvalidOperationException(
                "The countdown state prefix or values are invalid.");
        }

        public override string ToString() =>
            string.Create(
                CultureInfo.InvariantCulture,
                $"{StatePrefix}:{this.Current}:{this.CrashAtValue}:{this.Token}");
    }
}
