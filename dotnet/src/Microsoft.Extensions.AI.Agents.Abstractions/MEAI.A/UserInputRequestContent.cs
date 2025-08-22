// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Base class for user input request content.
/// </summary>
public abstract class UserInputRequestContent : AIContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="UserInputRequestContent"/> class.
    /// </summary>
    /// <param name="id">The ID to uniquely identify the user input request/response pair.</param>
    protected UserInputRequestContent(string id)
    {
        Id = Throw.IfNullOrWhitespace(id);
    }

    /// <summary>
    /// Gets the ID to uniquely identify the user input request/response pair.
    /// </summary>
    public string Id { get; }
}
