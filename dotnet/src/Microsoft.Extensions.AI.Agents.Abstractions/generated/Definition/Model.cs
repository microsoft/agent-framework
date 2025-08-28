// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an instance of Model.
/// </summary>
public sealed class Model
{
    /// <summary>
    /// Initializes a new instance of <see cref="Model"/>.
    /// </summary>
    public Model()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Model"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Model(IDictionary<string, object> props) : this()
    {
        Id = props.GetValueOrDefault<string>("id") ?? throw new ArgumentException("Properties must contain a property named: id", nameof(props));
        Connection = props.GetValueOrDefault<Connection?>("connection");
    }

    /// <summary>
    /// The unique identifier of the model
    /// </summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>
    /// The connection configuration for the model
    /// </summary>
    public Connection? Connection { get; set; }
}
