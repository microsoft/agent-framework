// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Generated.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Invocation.Stream;

/// <summary>
/// Defines a generator for nested stream events.
/// </summary>
/// <typeparam name="TAggregate">The type of aggregate to generate.</typeparam>
internal interface INestedStreamEventGenerator<TAggregate> where TAggregate : class
{
    /// <summary>
    /// Generates nested events groups asynchronously.
    /// </summary>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>An async enumerable of nested events groups.</returns>
    IAsyncEnumerable<NestedEventsGroup<TAggregate>> GenerateAsync(CancellationToken cancellationToken = default);
}

/// <summary>
/// Represents a group of nested stream events with an aggregate.
/// </summary>
/// <typeparam name="T">The type of aggregate.</typeparam>
internal class NestedEventsGroup<T> where T : class
{
    /// <summary>
    /// Gets or sets the function to create the aggregate.
    /// </summary>
    public required Func<T> CreateAggregate { get; init; }

    /// <summary>
    /// Gets or sets the events for this group.
    /// </summary>
    public required IAsyncEnumerable<ResponseStreamEvent> Events { get; init; }
}
