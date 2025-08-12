// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents a request for user approval of a function call.
/// </summary>
public class FunctionApprovalRequestContent : UserInputRequestContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="FunctionApprovalRequestContent"/> class.
    /// </summary>
    /// <param name="approvalId">The ID to uniquely identify the user input request/response pair.</param>
    /// <param name="functionCall">The function call that requires user approval.</param>
    public FunctionApprovalRequestContent(string approvalId, FunctionCallContent functionCall)
        : base(approvalId)
    {
        this.FunctionCall = Throw.IfNull(functionCall);
    }

    /// <summary>
    /// Gets or sets the function call that pre-invoke approval is required for.
    /// </summary>
    public FunctionCallContent FunctionCall { get; }

    /// <summary>
    /// Creates a <see cref="ChatMessage"/> representing an approval response.
    /// </summary>
    /// <returns>The <see cref="ChatMessage"/> representing the approval response.</returns>
    public ChatMessage Approve()
    {
        return new ChatMessage(ChatRole.User, [new FunctionApprovalResponseContent(this.Id, true, this.FunctionCall)]);
    }

    /// <summary>
    /// Creates a <see cref="ChatMessage"/> representing a rejection response.
    /// </summary>
    /// <returns>The <see cref="ChatMessage"/> representing the rejection response.</returns>
    public ChatMessage Reject()
    {
        return new ChatMessage(ChatRole.User, [new FunctionApprovalResponseContent(this.Id, false, this.FunctionCall)]);
    }
}
