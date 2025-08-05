// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// .
/// </summary>
public record ExecutorCapabilities
{
    /// <summary>
    /// .
    /// </summary>
    public string Id { get; init; }
    /// <summary>
    /// .
    /// </summary>
    public string Name { get; init; }
    /// <summary>
    /// .
    /// </summary>
    public Type ExecutorType { get; init; }
    /// <summary>
    /// .
    /// </summary>
    public ISet<Type> HandledMessageTypes { get; init; }
    /// <summary>
    /// .
    /// </summary>
    public bool IsInitialized { get; init; }
    /// <summary>
    /// .
    /// </summary>
    public ISet<string> StateKeys { get; init; }

    /// <summary>
    /// .
    /// </summary>
    public ExecutorCapabilities()
    {
        this.Id = string.Empty;
        this.Name = string.Empty;
        this.ExecutorType = typeof(Executor);
        this.HandledMessageTypes = new HashSet<Type>();
        this.IsInitialized = false;
        this.StateKeys = new HashSet<string>();
    }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="id"></param>
    /// <param name="name"></param>
    /// <param name="executorType"></param>
    /// <param name="handledMessageTypes"></param>
    /// <param name="isInitialized"></param>
    /// <param name="stateKeys"></param>
    public ExecutorCapabilities(string id, string name, Type executorType, ISet<Type> handledMessageTypes, bool isInitialized, ISet<string> stateKeys)
    {
        this.Id = id;
        this.Name = name;
        this.ExecutorType = executorType;
        this.HandledMessageTypes = handledMessageTypes;
        this.IsInitialized = isInitialized;
        this.StateKeys = stateKeys;
    }
}
