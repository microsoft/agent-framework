// Copyright (c) Microsoft. All rights reserved.

using Microsoft.DurableTask.Entities;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Durable entity that manages workflow state across activities within an orchestration run.
/// Each orchestration instance gets its own entity instance (keyed by orchestration instance ID),
/// ensuring state isolation between workflow runs. The entity is automatically cleaned up
/// when the orchestration completes.
/// </summary>
internal sealed class WorkflowSharedStateEntity : TaskEntity<WorkflowStateData>
{
    /// <summary>
    /// The entity name used for registration and lookup.
    /// </summary>
    public const string EntityName = "workflow-shared-state";

    /// <summary>
    /// Reads a state value by key and scope.
    /// </summary>
    /// <param name="request">The read request containing key and optional scope.</param>
    /// <returns>The serialized state value, or null if not found.</returns>
    public string? ReadState(WorkflowStateReadRequest request)
    {
        string scopeKey = GetScopeKey(request.ScopeName, request.Key);
        return this.State.Values.TryGetValue(scopeKey, out string? value) ? value : null;
    }

    /// <summary>
    /// Reads the entire state dictionary.
    /// </summary>
    /// <returns>A copy of the current state.</returns>
    public Dictionary<string, string> ReadAllState()
    {
        return new Dictionary<string, string>(this.State.Values);
    }

    /// <summary>
    /// Writes or updates a state value by key and scope.
    /// </summary>
    /// <param name="request">The write request containing key, scope, and value.</param>
    public void WriteState(WorkflowStateWriteRequest request)
    {
        string scopeKey = GetScopeKey(request.ScopeName, request.Key);

        if (request.Value is null)
        {
            this.State.Values.Remove(scopeKey);
        }
        else
        {
            this.State.Values[scopeKey] = request.Value;
        }
    }

    /// <summary>
    /// Gets all keys within a specific scope.
    /// </summary>
    /// <param name="scopeName">The scope name, or null for the default scope.</param>
    /// <returns>A collection of keys within the scope.</returns>
    public HashSet<string> GetStateKeys(string? scopeName)
    {
        string scopePrefix = GetScopePrefix(scopeName);
        HashSet<string> keys = [];

        foreach (string scopeKey in this.State.Values.Keys)
        {
            if (scopeKey.StartsWith(scopePrefix, StringComparison.Ordinal))
            {
                string key = scopeKey[scopePrefix.Length..];
                keys.Add(key);
            }
        }

        return keys;
    }

    /// <summary>
    /// Clears all state entries within a specific scope.
    /// </summary>
    /// <param name="scopeName">The scope name, or null for the default scope.</param>
    public void ClearScope(string? scopeName)
    {
        string scopePrefix = GetScopePrefix(scopeName);
        List<string> keysToRemove = [];

        foreach (string scopeKey in this.State.Values.Keys)
        {
            if (scopeKey.StartsWith(scopePrefix, StringComparison.Ordinal))
            {
                keysToRemove.Add(scopeKey);
            }
        }

        foreach (string key in keysToRemove)
        {
            this.State.Values.Remove(key);
        }
    }

    /// <summary>
    /// Deletes the entity, cleaning up all state.
    /// Called by the orchestration when it completes.
    /// </summary>
    public void Delete()
    {
        // Setting State to null tells the Durable Task framework to delete the entity.
        // The entity will be garbage collected after idle timeout.
        this.State = null!;
    }

    private static string GetScopeKey(string? scopeName, string key)
    {
        return $"{GetScopePrefix(scopeName)}{key}";
    }

    private static string GetScopePrefix(string? scopeName)
    {
        return scopeName is null ? "__default__:" : $"{scopeName}:";
    }
}

/// <summary>
/// Represents the internal state data for a workflow state entity.
/// </summary>
internal sealed class WorkflowStateData
{
    /// <summary>
    /// Gets the state dictionary mapping scope-prefixed keys to serialized values.
    /// </summary>
    public Dictionary<string, string> Values { get; init; } = [];
}

/// <summary>
/// Request model for reading workflow state.
/// </summary>
internal sealed class WorkflowStateReadRequest
{
    /// <summary>
    /// Gets or sets the state key.
    /// </summary>
    public string Key { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the optional scope name.
    /// </summary>
    public string? ScopeName { get; set; }
}

/// <summary>
/// Request model for writing workflow state.
/// </summary>
internal sealed class WorkflowStateWriteRequest
{
    /// <summary>
    /// Gets or sets the state key.
    /// </summary>
    public string Key { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the optional scope name.
    /// </summary>
    public string? ScopeName { get; set; }

    /// <summary>
    /// Gets or sets the serialized value, or null to delete the key.
    /// </summary>
    public string? Value { get; set; }
}
