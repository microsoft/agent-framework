// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// Helpers for building and driving <see cref="AgentResponseUpdate"/> sequences in tests.
/// </summary>
internal static class AgentUpdateTestHelpers
{
    /// <summary>
    /// The response identifier carried by updates built with <see cref="CreateFailedUpdate"/>.
    /// </summary>
    private const string FailedResponseId = "resp_test";

    /// <summary>
    /// Presents updates as the asynchronous sequence a <see cref="ResponseAgentProvider"/> returns.
    /// </summary>
    public static async IAsyncEnumerable<AgentResponseUpdate> ToAsyncEnumerableAsync(IEnumerable<AgentResponseUpdate> updates)
    {
        foreach (AgentResponseUpdate update in updates)
        {
            yield return update;
        }

        await Task.CompletedTask;
    }

    /// <summary>
    /// Runs updates through the provider's failure-detection transform, reproducing what
    /// <see cref="AzureAgentProvider"/> emits when streaming an agent run.
    /// </summary>
    public static async Task<List<AgentResponseUpdate>> ApplyFailureDetectionAsync(
        string agentName,
        params AgentResponseUpdate[] updates)
    {
        List<AgentResponseUpdate> results = [];

        await foreach (AgentResponseUpdate update in
            AzureAgentProvider.WithFailureDetectionAsync(ToAsyncEnumerableAsync(updates), agentName))
        {
            results.Add(update);
        }

        return results;
    }

    /// <summary>
    /// Builds the update shape <c>Microsoft.Extensions.AI.OpenAI</c> produces for a Responses
    /// <c>response.failed</c> event. Pass a null <paramref name="errorCode"/> to model a failure
    /// that carries no error detail.
    /// </summary>
    public static AgentResponseUpdate CreateFailedUpdate(string? errorCode, string? errorMessage)
    {
        string errorJson =
            errorCode is null
                ? "null"
                : $$"""{"code":"{{errorCode}}","message":"{{errorMessage}}"}""";

        string payload =
            $$"""
            {
              "type": "response.failed",
              "sequence_number": 1,
              "response": {
                "id": "{{FailedResponseId}}",
                "object": "response",
                "created_at": 1700000000,
                "status": "failed",
                "model": "gpt-test",
                "output": [],
                "error": {{errorJson}}
              }
            }
            """;

        StreamingResponseUpdate streamingUpdate =
            ModelReaderWriter.Read<StreamingResponseUpdate>(BinaryData.FromString(payload))!;

        // Guards the assumption the production unwrap depends on.
        Assert.IsType<StreamingResponseFailedUpdate>(streamingUpdate);

        ChatResponseUpdate chatUpdate =
            new(ChatRole.Assistant, (IList<AIContent>?)null)
            {
                ResponseId = FailedResponseId,
                RawRepresentation = streamingUpdate,
            };

        return new AgentResponseUpdate(chatUpdate);
    }
}
