﻿// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Configuration for an object with a string identifier. For example, <see cref="IIdentified"/> object.
/// </summary>
/// <param name="id">A unique identifier for the configurable object.</param>
public class Config(string? id = null)
{
    /// <summary>
    /// A unique identifier for the configurable object.
    /// </summary>
    /// <remarks>
    /// If not provided, the configured object will generate its own identifier.
    /// </remarks>
    public string? Id => id;
}

/// <summary>
/// Configuration for an object with a string identifier and options of type <typeparamref name="TOptions"/>.
/// </summary>
/// <typeparam name="TOptions">The type of options for the configurable object.</typeparam>
/// <param name="options">The options for the configurable object.</param>
/// <param name="id">A unique identifier for the configurable object.</param>
public class Config<TOptions>(TOptions? options = default, string? id = null) : Config(id)
{
    /// <summary>
    /// Options for the configured object.
    /// </summary>
    public TOptions? Options => options;
}
