// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Base class for content items to be processed by the Purview SDK.
/// </summary>
[JsonDerivedType(typeof(PurviewTextContent))]
[JsonDerivedType(typeof(PurviewBinaryContent))]
internal abstract class ContentBase : GraphDataTypeBase
{
    /// <summary>
    /// Creates a new instance of the <see cref="ContentBase"/> class.
    /// </summary>
    /// <param name="dataType">The graph data type of the content.</param>
    protected ContentBase(string dataType) : base(dataType)
    {
    }
}
