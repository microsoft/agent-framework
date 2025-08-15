// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents a request for user approval of a function call.
/// </summary>
public sealed class FunctionApprovalRequestContent : UserInputRequestContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="FunctionApprovalRequestContent"/> class.
    /// </summary>
    /// <param name="id">The ID to uniquely identify the function approval request/response pair.</param>
    /// <param name="functionCall">The function call that requires user approval.</param>
    public FunctionApprovalRequestContent(string id, FunctionCallContent functionCall)
        : base(id)
    {
        this.FunctionCall = Throw.IfNull(functionCall);
    }

    /// <summary>
    /// Gets the function call that pre-invoke approval is required for.
    /// </summary>
    public FunctionCallContent FunctionCall { get; }

    /// <summary>
    /// Creates a <see cref="FunctionApprovalResponseContent"/> representing an approval response.
    /// </summary>
    /// <returns>The <see cref="FunctionApprovalResponseContent"/> representing the approval response.</returns>
    public FunctionApprovalResponseContent CreateApproval()
    {
        return new FunctionApprovalResponseContent(this.Id, true, this.FunctionCall);
    }

    /// <summary>
    /// Creates a <see cref="FunctionApprovalResponseContent"/> representing a rejection response.
    /// </summary>
    /// <returns>The <see cref="FunctionApprovalResponseContent"/> representing the rejection response.</returns>
    public FunctionApprovalResponseContent CreateRejection()
    {
        return new FunctionApprovalResponseContent(this.Id, false, this.FunctionCall);
    }
}
