// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Represents a generic server tool that runs on a server
/// This tool type is designed for operations that require server-side execution
/// It may include features such as authentication, data storage, and long-running processes
/// This tool type is ideal for tasks that involve complex computations or access to secure resources
/// Server tools can be used to offload heavy processing from client applications
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class ServerTool : Tool
{
    /// <summary>
    /// Initializes a new instance of <see cref="ServerTool"/>.
    /// </summary>
    public ServerTool()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="ServerTool"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal ServerTool(IDictionary<string, object> props) : this()
    {
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Options = props.GetValueOrDefault<Dictionary<string, object>>("options") ?? throw new ArgumentException("Properties must contain a property named: options", nameof(props));
    }
    
    /// <summary>
    /// The type identifier for server tools
    /// </summary>
    
    public override string Type { get; set; } = "*";
    
    
    /// <summary>
    /// Configuration options for the server tool
    /// </summary>
    
    public Dictionary<string, object> Options { get; set; } = new Dictionary<string, object>();
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

