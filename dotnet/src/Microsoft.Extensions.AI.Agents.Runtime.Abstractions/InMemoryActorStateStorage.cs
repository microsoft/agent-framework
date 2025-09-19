// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Provides an in-memory implementation of <see cref="IActorStateStorage"/> for testing and development scenarios.
/// </summary>
/// <remarks>
/// <para>
/// This implementation stores all actor state in memory using concurrent dictionaries for thread safety.
/// State is not persisted across application restarts and is lost when the application terminates.
/// </para>
/// <para>
/// The implementation provides optimistic concurrency control using ETags. Each write operation must
/// provide the current ETag, and the operation will fail if the ETag has changed since the last read.
/// This ensures that concurrent modifications to the same actor state are handled correctly.
/// </para>
/// <para>
/// Supported operations:
/// <list type="bullet">
/// <item><description><see cref="SetValueOperation"/> - Sets a key-value pair in the actor's state</description></item>
/// <item><description><see cref="RemoveKeyOperation"/> - Removes a key from the actor's state</description></item>
/// <item><description><see cref="GetValueOperation"/> - Retrieves a value by key from the actor's state</description></item>
/// <item><description><see cref="ListKeysOperation"/> - Lists keys in the actor's state with optional prefix filtering</description></item>
/// </list>
/// </para>
/// <para>
/// This implementation is suitable for:
/// <list type="bullet">
/// <item><description>Unit testing scenarios</description></item>
/// <item><description>Development and prototyping</description></item>
/// <item><description>Single-process applications where persistence is not required</description></item>
/// </list>
/// </para>
/// <para>
/// For production scenarios requiring persistence, consider implementing a custom storage provider
/// that uses a database or other persistent storage mechanism.
/// </para>
/// </remarks>
/// <example>
/// <code>
/// // Create storage instance
/// var storage = new InMemoryActorStateStorage();
/// var actorId = new ActorId("MyActor", "instance1");
///
/// // Write some state
/// var writeOps = new List&lt;ActorStateWriteOperation&gt;
/// {
///     new SetValueOperation("name", JsonSerializer.SerializeToElement("John")),
///     new SetValueOperation("age", JsonSerializer.SerializeToElement(30))
/// };
/// var writeResult = await storage.WriteStateAsync(actorId, writeOps, "0");
///
/// // Read the state back
/// var readOps = new List&lt;ActorStateReadOperation&gt;
/// {
///     new GetValueOperation("name"),
///     new ListKeysOperation(null), // List all keys
///     new ListKeysOperation(null, "prefix_") // List keys starting with "prefix_"
/// };
/// var readResult = await storage.ReadStateAsync(actorId, readOps);
/// </code>
/// </example>
public sealed class InMemoryActorStateStorage : IActorStateStorage
{
    private static readonly ActivitySource ActivitySource = new("Microsoft.Extensions.AI.Agents.Runtime.Abstractions.InMemoryActorStateStorage");

    private readonly ConcurrentDictionary<ActorId, ActorState> _actorStates = [];
    private readonly object _lockObject = new();
    private long _globalETagCounter;

    /// <summary>
    /// Represents the internal state of an actor including its key-value pairs and ETag.
    /// </summary>
    private sealed class ActorState
    {
        public ConcurrentDictionary<string, JsonElement> Data { get; } = [];
        public string ETag { get; set; } = "0";
    }

    /// <inheritdoc/>
    public ValueTask<WriteResponse> WriteStateAsync(ActorId actorId, IReadOnlyCollection<ActorStateWriteOperation> operations, string etag, CancellationToken cancellationToken = default)
    {
        using var activity = ActivitySource.StartActivity("actor.state write");

        if (operations is null)
        {
            throw new ArgumentNullException(nameof(operations));
        }

        if (etag is null)
        {
            throw new ArgumentNullException(nameof(etag));
        }

        cancellationToken.ThrowIfCancellationRequested();

        // Set telemetry attributes
        SetActorAttributes(activity, actorId);
        SetStateAttributes(activity, "write", operations.Count, etag);

        try
        {
            lock (this._lockObject)
            {
                var actorState = this._actorStates.GetOrAdd(actorId, _ => new ActorState());

                // Check ETag for optimistic concurrency control
                if (actorState.ETag != etag)
                {
                    activity?
                        .SetTag("state.success", false)
                        .SetTag("error.type", "etag_mismatch")
                        .SetStatus(ActivityStatusCode.Error, "ETag mismatch - concurrent modification detected");

                    // Return failure with current ETag
                    return new ValueTask<WriteResponse>(new WriteResponse(actorState.ETag, success: false));
                }

                // Apply all operations
                var operationTypes = new List<string>();
                foreach (var operation in operations)
                {
                    switch (operation)
                    {
                        case SetValueOperation setValue:
                            actorState.Data[setValue.Key] = setValue.Value;
                            operationTypes.Add("set");
                            break;

                        case RemoveKeyOperation removeKey:
                            actorState.Data.TryRemove(removeKey.Key, out _);
                            operationTypes.Add("remove");
                            break;

                        default:
                            var errorMessage = $"Unsupported write operation type: {operation.GetType().Name}";
                            var exception = new InvalidOperationException(errorMessage);
                            SetErrorAttributes(activity, exception);
                            throw exception;
                    }
                }

                // Update ETag
                var newETag = Interlocked.Increment(ref this._globalETagCounter).ToString();
                actorState.ETag = newETag;

                // Set success attributes
                SetOperationStatus(activity, true);
                activity?
                    .SetTag("state.success", true)
                    .SetTag("state.new_etag", newETag)
                    .SetTag("state.operations", string.Join(",", operationTypes));

                return new ValueTask<WriteResponse>(new WriteResponse(newETag, success: true));
            }
        }
        catch (Exception ex)
        {
            SetErrorAttributes(activity, ex);
            throw;
        }
    }

    /// <inheritdoc/>
    public ValueTask<ReadResponse> ReadStateAsync(ActorId actorId, IReadOnlyCollection<ActorStateReadOperation> operations, CancellationToken cancellationToken = default)
    {
        using var activity = ActivitySource.StartActivity("actor.state read");

        if (operations is null)
        {
            throw new ArgumentNullException(nameof(operations));
        }

        cancellationToken.ThrowIfCancellationRequested();

        // Set telemetry attributes
        SetActorAttributes(activity, actorId);
        SetStateAttributes(activity, "read", operations.Count);

        try
        {
            var actorState = this._actorStates.GetOrAdd(actorId, _ => new ActorState());
            var results = new List<ActorReadResult>();
            var operationTypes = new List<string>();

            foreach (var operation in operations)
            {
                switch (operation)
                {
                    case GetValueOperation getValue:
                        var hasValue = actorState.Data.TryGetValue(getValue.Key, out var value);
                        results.Add(new GetValueResult(hasValue ? value : null));
                        operationTypes.Add($"get:{getValue.Key}");
                        break;

                    case ListKeysOperation listKeys:
                        var keys = actorState.Data.Keys.ToList();

                        // Filter keys by prefix if provided
                        if (!string.IsNullOrEmpty(listKeys.KeyPrefix))
                        {
                            keys = [.. keys.Where(key => key.StartsWith(listKeys.KeyPrefix, StringComparison.Ordinal))];
                        }

                        // Handle pagination if continuation token is provided
                        if (!string.IsNullOrEmpty(listKeys.ContinuationToken))
                        {
                            // For this simple implementation, we'll parse the continuation token as an index
                            if (int.TryParse(listKeys.ContinuationToken, out int startIndex) && startIndex < keys.Count)
                            {
                                keys = [.. keys.Skip(startIndex)];
                            }
                            else
                            {
                                keys = [];
                            }
                        }

                        // For simplicity, we'll return all keys without pagination
                        // In a real implementation, you might want to implement proper pagination
                        results.Add(new ListKeysResult(keys.AsReadOnly(), continuationToken: null));
                        operationTypes.Add($"list:{listKeys.KeyPrefix ?? "*"}");
                        break;

                    default:
                        var errorMessage = $"Unsupported read operation type: {operation.GetType().Name}";
                        var exception = new InvalidOperationException(errorMessage);
                        SetErrorAttributes(activity, exception);
                        throw exception;
                }
            }

            // Set success attributes
            SetOperationStatus(activity, true);
            activity?
                .SetTag("state.etag", actorState.ETag)
                .SetTag("state.operations", string.Join(",", operationTypes))
                .SetTag("state.success", true);

            return new ValueTask<ReadResponse>(new ReadResponse(actorState.ETag, results.AsReadOnly()));
        }
        catch (Exception ex)
        {
            SetErrorAttributes(activity, ex);
            throw;
        }
    }

    /// <summary>
    /// Clears all stored actor state. This method is primarily intended for testing scenarios.
    /// </summary>
    public void Clear()
    {
        lock (this._lockObject)
        {
            this._actorStates.Clear();
            Interlocked.Exchange(ref this._globalETagCounter, 0);
        }
    }

    /// <summary>
    /// Gets the current count of actors that have state stored.
    /// </summary>
    /// <returns>The number of actors with stored state.</returns>
    public int ActorCount => this._actorStates.Count;

    /// <summary>
    /// Gets the current count of keys stored for a specific actor.
    /// </summary>
    /// <param name="actorId">The actor identifier.</param>
    /// <returns>The number of keys stored for the specified actor, or 0 if the actor has no state.</returns>
    public int GetKeyCount(ActorId actorId) =>
        this._actorStates.TryGetValue(actorId, out var state) ? state.Data.Count : 0;

    /// <summary>
    /// Gets the current ETag for a specific actor.
    /// </summary>
    /// <param name="actorId">The actor identifier.</param>
    /// <returns>The current ETag for the specified actor, or "0" if the actor has no state.</returns>
    public string GetETag(ActorId actorId) =>
        this._actorStates.TryGetValue(actorId, out var state) ? state.ETag : "0";

    /// <summary>
    /// Sets actor attributes on an activity.
    /// </summary>
    /// <param name="activity">The activity to set attributes on.</param>
    /// <param name="actorId">The actor ID.</param>
    private static void SetActorAttributes(Activity? activity, ActorId actorId) =>
        activity?
            .SetTag("actor.id", actorId.ToString())
            .SetTag("actor.type", actorId.Type.Name);

    /// <summary>
    /// Sets state operation attributes on an activity.
    /// </summary>
    /// <param name="activity">The activity to set attributes on.</param>
    /// <param name="operationType">The type of state operation.</param>
    /// <param name="operationCount">Optional count of operations.</param>
    /// <param name="etag">Optional ETag value.</param>
    private static void SetStateAttributes(Activity? activity, string operationType, int? operationCount = null, string? etag = null)
    {
        if (activity is null)
        {
            return;
        }

        activity.SetTag("state.operation.type", operationType);

        if (operationCount.HasValue)
        {
            activity.SetTag("state.operation.count", operationCount.Value);
        }

        if (!string.IsNullOrEmpty(etag))
        {
            activity.SetTag("state.etag", etag);
        }
    }

    /// <summary>
    /// Sets success/failure status on an activity.
    /// </summary>
    /// <param name="activity">The activity to set status on.</param>
    /// <param name="success">Whether the operation was successful.</param>
    /// <param name="errorMessage">Optional error message for failures.</param>
    private static void SetOperationStatus(Activity? activity, bool success, string? errorMessage = null)
    {
        if (activity is null)
        {
            return;
        }

        if (success)
        {
            activity.SetStatus(ActivityStatusCode.Ok);
        }
        else
        {
            activity.SetStatus(ActivityStatusCode.Error, errorMessage);
        }
    }

    /// <summary>
    /// Sets error attributes on an activity.
    /// </summary>
    /// <param name="activity">The activity to set error attributes on.</param>
    /// <param name="exception">The exception that occurred.</param>
    private static void SetErrorAttributes(Activity? activity, Exception exception) =>
        activity?
            .SetTag("error.type", exception.GetType().Name)
            .SetTag("error.message", exception.Message)
            .SetStatus(ActivityStatusCode.Error, exception.Message)
            .AddEvent(new ActivityEvent("exception", DateTimeOffset.UtcNow, new ActivityTagsCollection
            {
                ["error.type"] = exception.GetType().Name,
                ["error.message"] = exception.Message,
                ["error.stack_trace"] = exception.StackTrace
            }));
}
