// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI;

/// <summary>
/// Base class for user input request content.
/// </summary>
public abstract class UserInputRequestContent : AIContent
{
    /// <summary>
    /// Gets or sets the ID to uniquely identify the user input request/response pair.
    /// </summary>
    public string ApprovalId { get; set; } = default!;
}
