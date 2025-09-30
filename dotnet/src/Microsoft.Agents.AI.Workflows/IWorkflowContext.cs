// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides services for an <see cref="Executor"/> during the execution of a workflow.
/// </summary>
public interface IWorkflowContext
{
    /// <summary>
    /// Adds an event to the workflow's output queue. These events will be raised to the caller of the workflow at the
    /// end of the current SuperStep.
    /// </summary>
    /// <param name="workflowEvent">The event to be raised.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    ValueTask AddEventAsync(WorkflowEvent workflowEvent);

    /// <summary>
    /// Queues a message to be sent to connected executors. The message will be sent during the next SuperStep.
    /// </summary>
    /// <param name="message">The message to be sent.</param>
    /// <param name="targetId">An optional identifier of the target executor. If null, the message is sent to all connected
    /// executors. If the target executor is not connected from this executor via an edge, it will still not receive the
    /// message.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    ValueTask SendMessageAsync(object message, string? targetId = null);

    /// <summary>
    /// Adds an output value to the workflow's output queue. These outputs will be bubbled out of the workflow using the
    /// <see cref="WorkflowOutputEvent"/>
    /// </summary>
    /// <remarks>
    /// The type of the output message must match one of the output types declared by the Executor. By default, the return
    /// types of registered message handlers are considered output types, unless otherwise specified using <see cref="ExecutorOptions"/>.
    /// </remarks>
    /// <param name="output">The output value to be returned.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    ValueTask YieldOutputAsync(object output);

    /// <summary>
    /// Adds a request to "halt" workflow execution at the end of the current SuperStep.
    /// </summary>
    /// <returns></returns>
    ValueTask RequestHaltAsync();

    /// <summary>
    /// Reads a state value from the workflow's state store. If no scope is provided, the executor's
    /// default scope is used.
    /// </summary>
    /// <typeparam name="T">The type of the state value.</typeparam>
    /// <param name="key">The key of the state value.</param>
    /// <param name = "scopeName" > An optional name that specifies the scope to read.If null, the default scope is
    /// used.</param>
    /// <returns>A <see cref="ValueTask{T}"/> representing the asynchronous operation.</returns>
    ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null);

    /// <summary>
    /// Asynchronously reads all state keys within the specified scope.
    /// </summary>
    /// <param name="scopeName">An optional name that specifies the scope to read. If null, the default scope is
    /// used.</param>
    ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null);

    /// <summary>
    /// Asynchronously updates the state of a queue entry identified by the specified key and optional scope.
    /// </summary>
    /// <remarks>
    /// Subsequent reads by this executor will result in the new value of the state. Other executors will only see
    /// the new state starting from the next SuperStep.
    /// </remarks>
    /// <typeparam name="T">The type of the value to associate with the queue entry.</typeparam>
    /// <param name="key">The unique identifier for the queue entry to update. Cannot be null or empty.</param>
    /// <param name="value">The value to set for the queue entry. If null, the entry's state may be cleared or reset depending on
    /// implementation.</param>
    /// <param name="scopeName">An optional name that specifies the scope to update. If null, the default scope is
    /// used.</param>
    /// <returns>A ValueTask that represents the asynchronous update operation.</returns>
    ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null);

    /// <summary>
    /// Asynchronously clears all state entries within the specified scope.
    ///
    /// This semantically equivalent to retrieving all keys in the scope and deleting them one-by-one.
    /// </summary>
    /// <remarks>
    /// Subsequent reads by this executor will not find any entries in the cleared scope. Other executors will only
    /// see the cleared state starting from the next SuperStep.
    /// </remarks>
    /// <param name="scopeName">An optional name that specifies the scope to clear. If null, the default scope is used.</param>
    /// <returns>A ValueTask that represents the asynchronous clear operation.</returns>
    ValueTask QueueClearScopeAsync(string? scopeName = null);
}
