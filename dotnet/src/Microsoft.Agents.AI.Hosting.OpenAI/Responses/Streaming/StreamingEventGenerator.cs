// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Streaming;

/// <summary>
/// Abstract base class for generating streaming events from <see cref="AIContent"/> instances
/// </summary>
internal abstract class StreamingEventGenerator
{
    /// <summary>
    /// Determines if the provided content is supported by this generator.
    /// </summary>
    /// <param name="content">The <see cref="AIContent"/> to check.</param>
    /// <returns>True if the content is supported, false otherwise.</returns>
    public abstract bool IsSupported(AIContent content);

    /// <summary>
    /// Processes a single <see cref="AIContent"/> instance and yields streaming events based on the current state.
    /// </summary>
    /// <param name="content">The <see cref="AIContent"/> to process.</param>
    /// <returns>An enumerable of streaming events generated from processing the content.</returns>
    public abstract IEnumerable<StreamingResponseEvent> ProcessContent(AIContent content);

    /// <summary>
    /// Completes the event generation and emits final events.
    /// </summary>
    /// <returns>An enumerable of final streaming events.</returns>
    public abstract IEnumerable<StreamingResponseEvent> Complete();
}
