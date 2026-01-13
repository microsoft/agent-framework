// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for working with <see cref="AgentResponse"/> and <see cref="AgentResponseUpdate"/> instances.
/// </summary>
public static class AgentResponseExtensions
{
    /// <summary>
    /// Creates a <see cref="ChatResponse"/> from an <see cref="AgentResponse"/> instance.
    /// </summary>
    /// <param name="response">The <see cref="AgentResponse"/> to convert.</param>
    /// <returns>A <see cref="ChatResponse"/> built from the specified <paramref name="response"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="response"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// If the <paramref name="response"/>'s <see cref="AgentResponse.RawRepresentation"/> is already a
    /// <see cref="ChatResponse"/> instance, that instance is returned directly.
    /// Otherwise, a new <see cref="ChatResponse"/> is created and populated with the data from the <paramref name="response"/>.
    /// The resulting instance is a shallow copy; any reference-type members (e.g. <see cref="AgentResponse.Messages"/>)
    /// will be shared between the two instances.
    /// </remarks>
    public static ChatResponse AsChatResponse(this AgentResponse response)
    {
        Throw.IfNull(response);

        return
            response.RawRepresentation as ChatResponse ??
            new()
            {
                AdditionalProperties = response.AdditionalProperties,
                CreatedAt = response.CreatedAt,
                Messages = response.Messages,
                RawRepresentation = response,
                ResponseId = response.ResponseId,
                Usage = response.Usage,
                ContinuationToken = response.ContinuationToken,
            };
    }

    /// <summary>
    /// Creates a <see cref="ChatResponseUpdate"/> from an <see cref="AgentResponseUpdate"/> instance.
    /// </summary>
    /// <param name="responseUpdate">The <see cref="AgentResponseUpdate"/> to convert.</param>
    /// <returns>A <see cref="ChatResponseUpdate"/> built from the specified <paramref name="responseUpdate"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="responseUpdate"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// If the <paramref name="responseUpdate"/>'s <see cref="AgentResponseUpdate.RawRepresentation"/> is already a
    /// <see cref="ChatResponseUpdate"/> instance, that instance is returned directly.
    /// Otherwise, a new <see cref="ChatResponseUpdate"/> is created and populated with the data from the <paramref name="responseUpdate"/>.
    /// The resulting instance is a shallow copy; any reference-type members (e.g. <see cref="AgentResponseUpdate.Contents"/>)
    /// will be shared between the two instances.
    /// </remarks>
    public static ChatResponseUpdate AsChatResponseUpdate(this AgentResponseUpdate responseUpdate)
    {
        Throw.IfNull(responseUpdate);

        return
            responseUpdate.RawRepresentation as ChatResponseUpdate ??
            new()
            {
                AdditionalProperties = responseUpdate.AdditionalProperties,
                AuthorName = responseUpdate.AuthorName,
                Contents = responseUpdate.Contents,
                CreatedAt = responseUpdate.CreatedAt,
                MessageId = responseUpdate.MessageId,
                RawRepresentation = responseUpdate,
                ResponseId = responseUpdate.ResponseId,
                Role = responseUpdate.Role,
                ContinuationToken = responseUpdate.ContinuationToken,
            };
    }

    /// <summary>
    /// Creates an asynchronous enumerable of <see cref="ChatResponseUpdate"/> instances from an asynchronous
    /// enumerable of <see cref="AgentResponseUpdate"/> instances.
    /// </summary>
    /// <param name="responseUpdates">The sequence of <see cref="AgentResponseUpdate"/> instances to convert.</param>
    /// <returns>An asynchronous enumerable of <see cref="ChatResponseUpdate"/> instances built from <paramref name="responseUpdates"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="responseUpdates"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// Each <see cref="AgentResponseUpdate"/> is converted to a <see cref="ChatResponseUpdate"/> using
    /// <see cref="AsChatResponseUpdate"/>.
    /// </remarks>
    public static async IAsyncEnumerable<ChatResponseUpdate> AsChatResponseUpdatesAsync(
        this IAsyncEnumerable<AgentResponseUpdate> responseUpdates)
    {
        Throw.IfNull(responseUpdates);

        await foreach (var responseUpdate in responseUpdates.ConfigureAwait(false))
        {
            yield return responseUpdate.AsChatResponseUpdate();
        }
    }

    /// <summary>
    /// Combines a sequence of <see cref="AgentResponseUpdate"/> instances into a single <see cref="AgentResponse"/>.
    /// </summary>
    /// <param name="updates">The sequence of updates to be combined into a single response.</param>
    /// <returns>A single <see cref="AgentResponse"/> that represents the combined state of all the updates.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="updates"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// As part of combining <paramref name="updates"/> into a single <see cref="AgentResponse"/>, the method will attempt to reconstruct
    /// <see cref="ChatMessage"/> instances. This includes using <see cref="AgentResponseUpdate.MessageId"/> to determine
    /// message boundaries, as well as coalescing contiguous <see cref="AIContent"/> items where applicable, e.g. multiple
    /// <see cref="TextContent"/> instances in a row may be combined into a single <see cref="TextContent"/>.
    /// </remarks>
    public static AgentResponse ToAgentResponse(
        this IEnumerable<AgentResponseUpdate> updates)
    {
        _ = Throw.IfNull(updates);

        AgentResponseDetails additionalDetails = new();
        ChatResponse chatResponse =
            AsChatResponseUpdatesWithAdditionalDetails(updates, additionalDetails)
            .ToChatResponse();

        return new AgentResponse(chatResponse)
        {
            AgentId = additionalDetails.AgentId,
        };
    }

    /// <summary>
    /// Asynchronously combines a sequence of <see cref="AgentResponseUpdate"/> instances into a single <see cref="AgentResponse"/>.
    /// </summary>
    /// <param name="updates">The asynchronous sequence of updates to be combined into a single response.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains a single <see cref="AgentResponse"/> that represents the combined state of all the updates.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="updates"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// <para>
    /// This is the asynchronous version of <see cref="ToAgentResponse(IEnumerable{AgentResponseUpdate})"/>.
    /// It performs the same combining logic but operates on an asynchronous enumerable of updates.
    /// </para>
    /// <para>
    /// As part of combining <paramref name="updates"/> into a single <see cref="AgentResponse"/>, the method will attempt to reconstruct
    /// <see cref="ChatMessage"/> instances. This includes using <see cref="AgentResponseUpdate.MessageId"/> to determine
    /// message boundaries, as well as coalescing contiguous <see cref="AIContent"/> items where applicable, e.g. multiple
    /// <see cref="TextContent"/> instances in a row may be combined into a single <see cref="TextContent"/>.
    /// </para>
    /// </remarks>
    public static Task<AgentResponse> ToAgentResponseAsync(
        this IAsyncEnumerable<AgentResponseUpdate> updates,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(updates);

        return ToAgentResponseAsync(updates, cancellationToken);

        static async Task<AgentResponse> ToAgentResponseAsync(
            IAsyncEnumerable<AgentResponseUpdate> updates,
            CancellationToken cancellationToken)
        {
            AgentResponseDetails additionalDetails = new();
            ChatResponse chatResponse = await
                AsChatResponseUpdatesWithAdditionalDetailsAsync(updates, additionalDetails, cancellationToken)
                .ToChatResponseAsync(cancellationToken)
                .ConfigureAwait(false);

            return new AgentResponse(chatResponse)
            {
                AgentId = additionalDetails.AgentId,
            };
        }
    }

    private static IEnumerable<ChatResponseUpdate> AsChatResponseUpdatesWithAdditionalDetails(
        IEnumerable<AgentResponseUpdate> updates,
        AgentResponseDetails additionalDetails)
    {
        foreach (var update in updates)
        {
            UpdateAdditionalDetails(update, additionalDetails);
            yield return update.AsChatResponseUpdate();
        }
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> AsChatResponseUpdatesWithAdditionalDetailsAsync(
        IAsyncEnumerable<AgentResponseUpdate> updates,
        AgentResponseDetails additionalDetails,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        await foreach (var update in updates.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            UpdateAdditionalDetails(update, additionalDetails);
            yield return update.AsChatResponseUpdate();
        }
    }

    private static void UpdateAdditionalDetails(AgentResponseUpdate update, AgentResponseDetails details)
    {
        if (update.AgentId is { Length: > 0 })
        {
            details.AgentId = update.AgentId;
        }
    }

    private sealed class AgentResponseDetails
    {
        public string? AgentId { get; set; }
    }
}
