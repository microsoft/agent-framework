// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

#pragma warning disable CA1812 // Internal class is apparently never instantiated
internal sealed class DefaultMessageTemplate : MessageTemplateBase
#pragma warning restore CA1812 // Internal class is apparently never instantiated
{
    public override bool When(MessageContext context) => true;

    // Buffer to convert response updates to chat messages.
    private readonly List<ChatMessage> _buffer = [];

    public DefaultMessageTemplate()
    {
        this.ChildContent = this.SelectTemplate;
    }

    private RenderFragment SelectTemplate(MessageContext messageContext)
    {
        if (messageContext.ChatMessage is not null)
        {
            var getRenderContents = messageContext.RenderContents();
            return CreateRenderMessage(
                messageContext.ChatMessage.Role,
                messageContext.ChatMessage.MessageId,
                getRenderContents);
        }
        else
        {
            var getRenderContents = messageContext.RenderContents();
            var updates = messageContext.ResponseUpdates ?? [];
            if (updates.Count == 0)
            {
                throw new InvalidOperationException("MessageContext must have either a ChatMessage or at least one ResponseUpdate.");
            }
            this._buffer.Clear();
            this._buffer.AddMessages(updates);
            if (this._buffer.Count != 1)
            {
                throw new InvalidOperationException("DefaultMessageTemplate only supports a single ResponseUpdate.");
            }

            return CreateRenderMessage(
                this._buffer[0].Role,
                this._buffer[0].MessageId,
                getRenderContents);
        }
    }

    private static RenderFragment CreateRenderMessage(
        ChatRole role,
        string? messageId,
        RenderFragment getRenderContents)
    {
        var roleClass = $"{role}-message";
        return builder =>
        {
            builder.OpenElement(0, "div");
            if (!string.IsNullOrEmpty(messageId))
            {
                builder.AddAttribute(1, "id", messageId);
            }
            else
            {
                builder.AddAttribute(2, "class", $"chat-message {roleClass}");
            }
            builder.AddContent(3, getRenderContents);
            builder.CloseElement();
        };
    }
}
