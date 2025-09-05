// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Connection configuration for AI agents.
/// `provider`, `type`, and `endpoint` are required properties here,
/// but this section can accept additional via options.
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class Connection
{
    /// <summary>
    /// Initializes a new instance of <see cref="Connection"/>.
    /// </summary>
    public Connection()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Connection"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Connection(IDictionary<string, object> props) : this()
    {
        Provider = props.GetValueOrDefault<string>("provider") ?? throw new ArgumentException("Properties must contain a property named: provider", nameof(props));
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Endpoint = props.GetValueOrDefault<string>("endpoint") ?? throw new ArgumentException("Properties must contain a property named: endpoint", nameof(props));
        Options = props.GetValueOrDefault<Dictionary<string, object>?>("options");
    }
    
    /// <summary>
    /// The unique provider of the connection
    /// </summary>
    
    public string Provider { get; set; } = string.Empty;
    
    
    /// <summary>
    /// The type of connection used to tell the runtime how to load and execute the agent
    /// </summary>
    
    public string Type { get; set; } = string.Empty;
    
    
    /// <summary>
    /// The endpoint URL for the connection
    /// </summary>
    
    public string Endpoint { get; set; } = string.Empty;
    
    
    /// <summary>
    /// Additional options for model execution
    /// </summary>
    
    public Dictionary<string, object>? Options { get; set; }
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

