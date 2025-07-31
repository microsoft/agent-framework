// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI;

/// <summary>
/// Base class for user input response content.
/// </summary>
public abstract class UserInputResponseContent : AIContent
{
    /// <summary>
    /// Gets or sets the ID to uniquely identify the user input request/response pair.
    /// </summary>
    public string ApprovalId { get; set; } = default!;
}
