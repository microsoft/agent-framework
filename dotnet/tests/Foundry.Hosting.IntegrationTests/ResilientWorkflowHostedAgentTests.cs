// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

#pragma warning disable OPENAI001 // Experimental Responses API surfaces

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Live long-running and crash-recovery tests for resilient background Responses hosting.
/// </summary>
[Trait("Category", "FoundryHostedAgents")]
public sealed class ResilientWorkflowHostedAgentTests(ResilientWorkflowHostedAgentFixture fixture)
    : IClassFixture<ResilientWorkflowHostedAgentFixture>
{
    private static readonly TimeSpan s_completionTimeout = TimeSpan.FromMinutes(6);
    private readonly ResilientWorkflowHostedAgentFixture _fixture = fixture;

    [Fact]
    public async Task BackgroundResponse_ContinuesWithoutClientConnectionAsync()
    {
        // Arrange
        string token = Guid.NewGuid().ToString("N");
        CreateResponseOptions options = CreateBackgroundRequest($"long:{token}");
        var responses = this._fixture.AgentOpenAIClient.GetProjectResponsesClient();
        Stopwatch stopwatch = Stopwatch.StartNew();

        // Act
        ResponseResult accepted = (await responses.CreateResponseAsync(options)).Value;
        TimeSpan acceptanceTime = stopwatch.Elapsed;

        // Leave the response alone while its deterministic delay runs.
        await Task.Delay(TimeSpan.FromSeconds(25));
        ResponseWaitResult waitResult = await WaitForTerminalAsync(responses, accepted.Id, s_completionTimeout);

        // Assert
        Assert.True(accepted.Status is ResponseStatus.Queued or ResponseStatus.InProgress);
        Assert.True(acceptanceTime < TimeSpan.FromSeconds(10), $"Background acceptance took {acceptanceTime}.");
        Assert.Equal(ResponseStatus.Completed, waitResult.Response.Status);
        Assert.Contains($"LONG-RUN-COMPLETE:{token}", waitResult.Response.GetOutputText(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task BackgroundResponse_ProcessCrash_RecoversAndCompletesAsync()
    {
        // Arrange
        string token = Guid.NewGuid().ToString("N");
        CreateResponseOptions options = CreateBackgroundRequest($"crash:{token}");
        var responses = this._fixture.AgentOpenAIClient.GetProjectResponsesClient();
        Stopwatch stopwatch = Stopwatch.StartNew();

        // Act
        ResponseResult accepted = (await responses.CreateResponseAsync(options)).Value;
        TimeSpan acceptanceTime = stopwatch.Elapsed;
        ResponseWaitResult waitResult = await WaitForTerminalAsync(responses, accepted.Id, s_completionTimeout);

        // Assert: this token is emitted only after a new process observes the crash marker written
        // immediately before Environment.Exit.
        Assert.True(accepted.Status is ResponseStatus.Queued or ResponseStatus.InProgress);
        Assert.True(
            waitResult.SawSessionNotReady
                || waitResult.SawResponseNotFound
                || waitResult.LongestPollDuration > acceptanceTime,
            "Expected recovery to return transient HTTP 424/404 or take longer than background acceptance. " +
            $"Acceptance: {acceptanceTime}; longest poll: {waitResult.LongestPollDuration}.");
        Assert.Equal(ResponseStatus.Completed, waitResult.Response.Status);
        Assert.Contains(
            $"CRASH-RECOVERED:{token}:PROCESS-CHANGED",
            waitResult.Response.GetOutputText(),
            StringComparison.Ordinal);
    }

    [Fact]
    public async Task BackgroundCountdown_ProcessCrash_RecoversAndReplaysAllUpdatesAsync()
    {
        // Arrange
        const int Target = 20;
        const int CrashAfterCount = 10;
        string token = Guid.NewGuid().ToString("N");
        List<string> expected =
        [
            .. Enumerable.Range(1, Target)
                .Reverse()
                .Select(value => value.ToString(System.Globalization.CultureInfo.InvariantCulture)),
            "Countdown complete.",
        ];
        AIAgent agent = this._fixture.Agent;
        AgentSession session = await agent.CreateSessionAsync();
        AgentRunOptions initialOptions = new() { AllowBackgroundResponses = true };
        using CancellationTokenSource timeoutSource = new(s_completionTimeout);

        // Act
        StreamCapture before = await CaptureUntilDisconnectAsync(
            agent,
            session,
            $"countdown:{Target}:{CrashAfterCount}:{token}",
            initialOptions,
            "before",
            timeoutSource.Token);

        ResponseContinuationToken continuationToken = before.ContinuationToken
            ?? throw new InvalidOperationException(
                "The interrupted stream did not provide a continuation token.");
        AgentRunOptions recoveryOptions = new()
        {
            AllowBackgroundResponses = true,
            ContinuationToken = continuationToken,
        };
        StreamCapture recovered = await CaptureToCompletionWithRetryAsync(
            agent,
            session,
            recoveryOptions,
            "recovered",
            before.CompletedMessageIds,
            timeoutSource.Token);

        List<string> recoveredCountdown = [.. before.Texts, .. recovered.Texts];
        string responseId = before.ResponseId
            ?? recovered.ResponseId
            ?? throw new InvalidOperationException(
                "The countdown stream did not provide a response ID.");
        AgentRunOptions replayOptions = new()
        {
            AllowBackgroundResponses = true,
            ContinuationToken = CreateReplayFromStartToken(responseId),
        };
        StreamCapture replayed = await CaptureToCompletionWithRetryAsync(
            agent,
            session,
            replayOptions,
            "replayed",
            existingMessageIds: null,
            timeoutSource.Token);

        // Assert
        Assert.Equal(expected.Take(CrashAfterCount), before.Texts);
        Assert.Equal(expected, recoveredCountdown);
        Assert.Equal(Target, CountCountdownUpdates(recoveredCountdown));
        Assert.Equal(expected, replayed.Texts);
        Assert.Equal(Target, CountCountdownUpdates(replayed.Texts));
    }

    private static CreateResponseOptions CreateBackgroundRequest(string input)
    {
        CreateResponseOptions options = new()
        {
            BackgroundModeEnabled = true,
            StoredOutputEnabled = true,
        };
        options.InputItems.Add(ResponseItem.CreateUserMessageItem(input));
        return options;
    }

    private static async Task<StreamCapture> CaptureUntilDisconnectAsync(
        AIAgent agent,
        AgentSession session,
        string input,
        AgentRunOptions options,
        string phase,
        CancellationToken cancellationToken)
    {
        StreamCapture capture = new();

        try
        {
            await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(
                input,
                session,
                options,
                cancellationToken))
            {
                capture.Observe(update, phase);
            }
        }
        catch (ClientResultException exception)
            when (IsTransientRecoveryStatus(exception.Status))
        {
        }
        catch (HttpRequestException)
        {
        }

        return capture;
    }

    private static async Task<StreamCapture> CaptureToCompletionWithRetryAsync(
        AIAgent agent,
        AgentSession session,
        AgentRunOptions options,
        string phase,
        IEnumerable<string>? existingMessageIds,
        CancellationToken cancellationToken)
    {
        StreamCapture capture = new(existingMessageIds);

        while (!capture.ResponseCompleted)
        {
            if (capture.ContinuationToken is not null)
            {
                options.ContinuationToken = capture.ContinuationToken;
            }

            try
            {
                await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(
                    session,
                    options,
                    cancellationToken))
                {
                    capture.Observe(update, phase);
                }
            }
            catch (ClientResultException exception)
                when (IsTransientRecoveryStatus(exception.Status))
            {
            }
            catch (HttpRequestException)
            {
            }

            if (!capture.ResponseCompleted)
            {
                await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);
            }
        }

        return capture;
    }

    private static ResponseContinuationToken CreateReplayFromStartToken(
        string responseId)
    {
        ResponseContinuationToken innerToken =
            ResponseContinuationToken.FromBytes(
                JsonSerializer.SerializeToUtf8Bytes(
                    new { responseId }));
        string serializedInnerToken = JsonSerializer.Serialize(
            innerToken,
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(
                typeof(ResponseContinuationToken)));
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(
            new
            {
                type = "chatClientAgentContinuationToken",
                innerToken = serializedInnerToken,
            });
        return ResponseContinuationToken.FromBytes(bytes);
    }

    private static bool IsTransientRecoveryStatus(int status) =>
        status is 404 or 424 or 500 or 502 or 503;

    private static int CountCountdownUpdates(IEnumerable<string> texts) =>
        texts.Count(text => text != "Countdown complete.");

    private static async Task<ResponseWaitResult> WaitForTerminalAsync(
        ResponsesClient responses,
        string responseId,
        TimeSpan timeout)
    {
        bool sawSessionNotReady = false;
        bool sawResponseNotFound = false;
        TimeSpan longestPollDuration = TimeSpan.Zero;
        var deadline = DateTimeOffset.UtcNow + timeout;
        while (DateTimeOffset.UtcNow < deadline)
        {
            ResponseResult response;
            Stopwatch pollStopwatch = Stopwatch.StartNew();
            try
            {
                response = (await responses.GetResponseAsync(responseId)).Value;
            }
            catch (ClientResultException ex) when (ex.Status == 424)
            {
                longestPollDuration = Max(longestPollDuration, pollStopwatch.Elapsed);
                sawSessionNotReady = true;
                await Task.Delay(TimeSpan.FromSeconds(2));
                continue;
            }
            catch (ClientResultException ex) when (ex.Status == 404)
            {
                longestPollDuration = Max(longestPollDuration, pollStopwatch.Elapsed);
                sawResponseNotFound = true;
                await Task.Delay(TimeSpan.FromSeconds(2));
                continue;
            }

            longestPollDuration = Max(longestPollDuration, pollStopwatch.Elapsed);
            if (response.Status is ResponseStatus.Completed)
            {
                return new(
                    response,
                    sawSessionNotReady,
                    sawResponseNotFound,
                    longestPollDuration);
            }

            if (response.Status is ResponseStatus.Cancelled or ResponseStatus.Failed or ResponseStatus.Incomplete)
            {
                throw new InvalidOperationException(
                    $"Response '{responseId}' terminated with status '{response.Status}': {response.Error?.Message}");
            }

            await Task.Delay(TimeSpan.FromSeconds(2));
        }

        throw new TimeoutException($"Response '{responseId}' did not complete within {timeout}.");

        static TimeSpan Max(TimeSpan left, TimeSpan right) => left >= right ? left : right;
    }

    private sealed record ResponseWaitResult(
        ResponseResult Response,
        bool SawSessionNotReady,
        bool SawResponseNotFound,
        TimeSpan LongestPollDuration);

    private sealed class StreamCapture
    {
        private readonly HashSet<string> _completedMessageIds;

        public StreamCapture(
            IEnumerable<string>? existingMessageIds = null)
        {
            this._completedMessageIds = new(
                existingMessageIds ?? [],
                StringComparer.Ordinal);
        }

        public List<string> Texts { get; } = [];

        public IReadOnlyCollection<string> CompletedMessageIds =>
            this._completedMessageIds;

        public string? ResponseId { get; private set; }

        public ResponseContinuationToken? ContinuationToken { get; private set; }

        public bool ResponseCompleted { get; private set; }

        public void Observe(AgentResponseUpdate update, string phase)
        {
            object? rawRepresentation =
                update.RawRepresentation is ChatResponseUpdate chatResponseUpdate
                    ? chatResponseUpdate.RawRepresentation
                    : update.RawRepresentation;

            if (update.ContinuationToken is { } continuationToken)
            {
                this.ContinuationToken = continuationToken;
            }

            if (!string.IsNullOrWhiteSpace(update.ResponseId))
            {
                this.ResponseId = update.ResponseId;
            }

            if (rawRepresentation is StreamingResponseOutputItemDoneUpdate
                {
                    Item: MessageResponseItem message
                }
                && this._completedMessageIds.Add(message.Id))
            {
                this.AddMessage(message, phase);
            }

            ResponseResult? responseSnapshot = rawRepresentation switch
            {
                StreamingResponseCreatedUpdate created => created.Response,
                StreamingResponseInProgressUpdate inProgress =>
                    inProgress.Response,
                StreamingResponseCompletedUpdate completed =>
                    completed.Response,
                _ => null,
            };
            if (responseSnapshot is not null)
            {
                foreach (MessageResponseItem snapshotMessage in
                    responseSnapshot.OutputItems.OfType<MessageResponseItem>())
                {
                    if (this._completedMessageIds.Add(snapshotMessage.Id))
                    {
                        this.AddMessage(snapshotMessage, phase);
                    }
                }
            }

            if (rawRepresentation is StreamingResponseCompletedUpdate)
            {
                this.ResponseCompleted = true;
            }
            else if (rawRepresentation is StreamingResponseFailedUpdate failed)
            {
                throw new InvalidOperationException(
                    $"Response '{failed.Response.Id}' failed: " +
                    failed.Response.Error?.Message);
            }
        }

        private void AddMessage(
            MessageResponseItem message,
            string phase)
        {
            string text = string.Concat(
                message.Content
                    .Where(content =>
                        content.Kind is ResponseContentPartKind.OutputText)
                    .Select(content => content.Text));
            if (!string.IsNullOrEmpty(text))
            {
                this.Texts.Add(text);
                Console.WriteLine($"{phase} > {text}");
            }
        }
    }
}
