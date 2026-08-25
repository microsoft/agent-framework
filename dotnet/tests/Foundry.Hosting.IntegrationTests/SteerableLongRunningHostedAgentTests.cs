// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
using Foundry.Hosting.IntegrationTests.Fixtures;
using OpenAI.Responses;

#pragma warning disable OPENAI001 // Experimental Responses API surfaces

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Live steering tests for an active long-running MAF turn.
/// </summary>
[Trait("Category", "FoundryHostedAgents")]
public sealed class SteerableLongRunningHostedAgentTests(
    SteerableLongRunningHostedAgentFixture fixture)
    : IClassFixture<SteerableLongRunningHostedAgentFixture>
{
    private static readonly TimeSpan s_completionTimeout = TimeSpan.FromMinutes(6);
    private readonly SteerableLongRunningHostedAgentFixture _fixture = fixture;

    [Fact]
    public async Task ActiveTurn_QueuesSteeringThenRunsItOnTheSameSessionAsync()
    {
        // Arrange
        string token = Guid.NewGuid().ToString("N");
        string conversationId = await this._fixture.CreateConversationAsync();
        var responses = this._fixture.AgentOpenAIClient.GetProjectResponsesClient();

        try
        {
            CreateResponseOptions firstOptions =
                CreateBackgroundRequest(conversationId, $"first:{token}");
            string firstResponseId = await StartStreamingAndWaitForOutputAsync(
                responses,
                firstOptions,
                $"FIRST-STARTED:{token}",
                s_completionTimeout);

            // Act
            CreateResponseOptions steeringOptions =
                CreateBackgroundRequest(conversationId, $"steer:{token}");
            ResponseResult steering = (await responses.CreateResponseAsync(steeringOptions)).Value;

            // Assert
            Assert.Equal(ResponseStatus.Queued, steering.Status);

            ResponseResult firstCompleted =
                await WaitForTerminalAsync(
                    responses,
                    firstResponseId,
                    s_completionTimeout);
            ResponseResult steeringCompleted =
                await WaitForTerminalAsync(responses, steering.Id, s_completionTimeout);

            Assert.Equal(ResponseStatus.Completed, firstCompleted.Status);
            Assert.Equal(ResponseStatus.Completed, steeringCompleted.Status);
            Assert.Contains(
                $"STEERED-COMPLETE:{token}:SESSION-TURN-2:MAX-CONCURRENCY-1",
                steeringCompleted.GetOutputText(),
                StringComparison.Ordinal);
        }
        finally
        {
            await this._fixture.DeleteConversationAsync(conversationId);
        }
    }

    private static CreateResponseOptions CreateBackgroundRequest(
        string conversationId,
        string input)
    {
        CreateResponseOptions options = new()
        {
            AgentConversationId = conversationId,
            BackgroundModeEnabled = true,
            StoredOutputEnabled = true,
        };
        options.InputItems.Add(ResponseItem.CreateUserMessageItem(input));
        return options;
    }

    private static async Task<string> StartStreamingAndWaitForOutputAsync(
        ResponsesClient responses,
        CreateResponseOptions options,
        string expected,
        TimeSpan timeout)
    {
        using CancellationTokenSource timeoutSource = new(timeout);
        string? responseId = null;
        StringBuilder text = new();

        await foreach (StreamingResponseUpdate update in responses
            .CreateResponseStreamingAsync(options, timeoutSource.Token)
            .WithCancellation(timeoutSource.Token))
        {
            switch (update)
            {
                case StreamingResponseCreatedUpdate created:
                    responseId = created.Response.Id;
                    break;

                case StreamingResponseOutputTextDeltaUpdate delta:
                    text.Append(delta.Delta);
                    if (text.ToString().Contains(expected, StringComparison.Ordinal))
                    {
                        return responseId
                            ?? throw new InvalidOperationException(
                                "The stream emitted text before response.created.");
                    }
                    break;

                case StreamingResponseFailedUpdate failed:
                    throw new InvalidOperationException(
                        $"Response '{failed.Response.Id}' failed: " +
                        failed.Response.Error?.Message);
            }
        }

        throw new InvalidOperationException(
            $"The response stream ended before emitting '{expected}'.");
    }

    private static async Task<ResponseResult> WaitForTerminalAsync(
        ResponsesClient responses,
        string responseId,
        TimeSpan timeout)
    {
        var deadline = DateTimeOffset.UtcNow + timeout;
        while (DateTimeOffset.UtcNow < deadline)
        {
            ResponseResult? response = await TryGetResponseAsync(responses, responseId);
            if (response?.Status is ResponseStatus.Completed)
            {
                return response;
            }

            if (response is not null)
            {
                ThrowIfTerminalFailure(responseId, response);
            }

            await Task.Delay(TimeSpan.FromSeconds(2));
        }

        throw new TimeoutException(
            $"Response '{responseId}' did not complete within {timeout}.");
    }

    private static async Task<ResponseResult?> TryGetResponseAsync(
        ResponsesClient responses,
        string responseId)
    {
        try
        {
            return (await responses.GetResponseAsync(responseId)).Value;
        }
        catch (ClientResultException ex) when (ex.Status is 404 or 424)
        {
            return null;
        }
    }

    private static void ThrowIfTerminalFailure(
        string responseId,
        ResponseResult response)
    {
        if (response.Status is ResponseStatus.Cancelled
            or ResponseStatus.Failed
            or ResponseStatus.Incomplete)
        {
            throw new InvalidOperationException(
                $"Response '{responseId}' terminated with status '{response.Status}': " +
                response.Error?.Message);
        }
    }
}
