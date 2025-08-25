// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Base class for user input response content.
/// </summary>
public abstract class UserInputResponseContent : AIContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="UserInputResponseContent"/> class.
    /// </summary>
    /// <param name="id">The ID to uniquely identify the user input request/response pair.</param>
    protected UserInputResponseContent(string id)
    {
        Id = Throw.IfNullOrWhitespace(id);
    }

    /// <summary>
    /// Gets the ID to uniquely identify the user input request/response pair.
    /// </summary>
    public string Id { get; }
}
