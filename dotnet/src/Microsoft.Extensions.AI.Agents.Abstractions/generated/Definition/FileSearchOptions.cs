// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Options for file search.
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class FileSearchOptions
{
    /// <summary>
    /// Initializes a new instance of <see cref="FileSearchOptions"/>.
    /// </summary>
    public FileSearchOptions()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="FileSearchOptions"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal FileSearchOptions(IDictionary<string, object> props) : this()
    {
        MaxNumResults = props.GetValueOrDefault<object?>("maxNumResults");
        RankingOptions = props.GetValueOrDefault<FileSearchRankingOptions?>("rankingOptions");
    }
    
    /// <summary>
    /// The maximum number of search results to return.
    /// </summary>
    
    public object? MaxNumResults { get; set; }
    
    
    /// <summary>
    /// Options for ranking file search results.
    /// </summary>
    
    public FileSearchRankingOptions? RankingOptions { get; set; }
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

