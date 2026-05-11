// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Optional interface implemented by request payload types that wrap underlying
/// AI content (such as <see cref="FunctionCallContent"/> or
/// <see cref="ToolApprovalRequestContent"/>) and define a paired response envelope.
/// </summary>
/// <remarks>
/// <para>
/// This abstraction allows higher-level layers (e.g., declarative workflows) to define
/// their own request/response envelope types while still allowing
/// <c>WorkflowSession</c> to surface the inner content to hosts on the request side
/// and to wrap incoming responses back into the envelope on the response side -
/// without the runtime taking a reference back to the higher-level layer.
/// </para>
/// <para>
/// When an <c>ExternalRequest.Data</c> payload implements this interface, the
/// runtime uses <see cref="GetInnerRequestContent"/> to drive wire serialization
/// for hosts (so a host receives a normal <see cref="FunctionCallContent"/> or
/// <see cref="ToolApprovalRequestContent"/>), and uses <see cref="CreateResponse"/>
/// to wrap the host's response payload back into the envelope expected by the
/// workflow's request port.
/// </para>
/// </remarks>
public interface IExternalRequestEnvelope
{
    /// <summary>
    /// Returns the inner AI content that should be delivered to the host on the wire.
    /// Typically a <see cref="FunctionCallContent"/> or <see cref="ToolApprovalRequestContent"/>.
    /// </summary>
    /// <returns>The inner content, or <c>null</c> if no suitable inner content is available.</returns>
    AIContent? GetInnerRequestContent();

    /// <summary>
    /// Wraps the supplied response messages into the envelope's matching response type
    /// for delivery to the workflow's request port.
    /// </summary>
    /// <param name="messages">The response messages, typically containing a
    /// <see cref="FunctionResultContent"/> and/or <see cref="ToolApprovalResponseContent"/>.</param>
    /// <returns>An instance of the envelope's response type wrapping <paramref name="messages"/>.</returns>
    object CreateResponse(IList<ChatMessage> messages);
}
