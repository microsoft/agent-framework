// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Extension methods for reporting usage aggregated by <see cref="UsageAggregator"/> on the response that
/// concludes a run.
/// </summary>
internal static class UsageAggregationExtensions
{
    /// <summary>
    /// Reports <paramref name="aggregatedUsage"/> on <paramref name="response"/> in place of the usage it
    /// carries, which typically covers only the final service call of a run.
    /// </summary>
    /// <param name="response">The response produced by the final call of the run.</param>
    /// <param name="aggregatedUsage">The usage accumulated across every call that made up the run.</param>
    /// <param name="messages">
    /// The messages the response should carry, or <see langword="null"/> to keep those it already has. Used
    /// when a run returns a transcript spanning multiple calls.
    /// </param>
    /// <returns>The same <paramref name="response"/> instance, updated in place.</returns>
    /// <remarks>
    /// The supplied response is updated rather than copied, so that a derived response type returned by an
    /// inner client (along with any state it carries) survives the aggregation. This matches how
    /// <see cref="FunctionInvokingChatClient"/> reports the usage it accumulates across function-calling
    /// iterations. Only the response is mutated: <paramref name="aggregatedUsage"/> is a freshly combined
    /// instance, so no <see cref="UsageDetails"/> owned by an inner client is modified.
    /// </remarks>
    public static ChatResponse ApplyAggregatedUsage(this ChatResponse response, UsageDetails? aggregatedUsage, IList<ChatMessage>? messages = null)
    {
        if (messages is not null)
        {
            response.Messages = messages;
        }

        response.Usage = aggregatedUsage;
        return response;
    }

    /// <summary>
    /// Reports <paramref name="aggregatedUsage"/> on <paramref name="response"/> in place of the usage it
    /// carries, which typically covers only the final invocation of a run.
    /// </summary>
    /// <param name="response">The response produced by the final invocation of the run.</param>
    /// <param name="aggregatedUsage">The usage accumulated across every invocation that made up the run.</param>
    /// <param name="messages">
    /// The messages the response should carry, or <see langword="null"/> to keep those it already has. Used
    /// when a run returns a transcript spanning multiple invocations.
    /// </param>
    /// <returns>The same <paramref name="response"/> instance, updated in place.</returns>
    /// <remarks>
    /// The supplied response is updated rather than copied, so that a derived response type returned by an
    /// inner agent (such as <see cref="AgentResponse{T}"/>, along with any state it carries) survives the
    /// aggregation. Only the response is mutated: <paramref name="aggregatedUsage"/> is a freshly combined
    /// instance, so no <see cref="UsageDetails"/> owned by an inner agent is modified.
    /// </remarks>
    public static AgentResponse ApplyAggregatedUsage(this AgentResponse response, UsageDetails? aggregatedUsage, IList<ChatMessage>? messages = null)
    {
        if (messages is not null)
        {
            response.Messages = messages;
        }

        response.Usage = aggregatedUsage;
        return response;
    }
}
