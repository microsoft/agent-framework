// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents a request for user approval of a function call.
/// </summary>
public class FunctionApprovalRequestContent : UserInputRequestContent
{
    /// <summary>
    /// Gets or sets the function call that pre-invoke approval is required for.
    /// </summary>
    public FunctionCallContent FunctionCall { get; set; } = default!;

    /// <summary>
    /// Creates a <see cref="ChatMessage"/> representing an approval response.
    /// </summary>
    /// <returns>The <see cref="ChatMessage"/> representing the approval response.</returns>
    public ChatMessage Approve()
    {
        return new ChatMessage(ChatRole.User,
        [
            new FunctionApprovalResponseContent
            {
                ApprovalId = this.ApprovalId,
                Approved = true,
                FunctionCall = this.FunctionCall
            }
        ]);
    }

    /// <summary>
    /// Creates a <see cref="ChatMessage"/> representing a rejection response.
    /// </summary>
    /// <returns>The <see cref="ChatMessage"/> representing the rejection response.</returns>
    public ChatMessage Reject()
    {
        return new ChatMessage(ChatRole.User,
        [
            new FunctionApprovalResponseContent
            {
                ApprovalId = this.ApprovalId,
                Approved = false,
                FunctionCall = this.FunctionCall
            }
        ]);
    }
}
