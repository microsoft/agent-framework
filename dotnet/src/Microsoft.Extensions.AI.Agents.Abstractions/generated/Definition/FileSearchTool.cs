// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// A tool for searching files.
/// This tool allows an AI agent to search for files based on a query.
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class FileSearchTool : Tool
{
    /// <summary>
    /// Initializes a new instance of <see cref="FileSearchTool"/>.
    /// </summary>
    public FileSearchTool()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="FileSearchTool"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal FileSearchTool(IDictionary<string, object> props) : this()
    {
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Options = props.GetValueOrDefault<FileSearchOptions>("options") ?? throw new ArgumentException("Properties must contain a property named: options", nameof(props));
    }
    
    /// <summary>
    /// The type identifier for file search tools
    /// </summary>
    
    public override string Type { get; set; } = "file_search";
    
    
    /// <summary>
    /// The options for the file search tool
    /// </summary>
    
    public FileSearchOptions Options { get; set; } = new FileSearchOptions();
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

