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
            // Return a render fragment that checks visibility at render time
            // This is important because message contents may change during streaming
            return CreateRenderMessage(
                messageContext.ChatMessage,
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
                this._buffer[0],
                getRenderContents);
        }
    }

    /// <summary>
    /// Checks if a message has any visible content that should be displayed.
    /// Messages that only contain FunctionCallContent or FunctionResultContent
    /// are internal tool messages and should not be rendered as chat bubbles.
    /// </summary>
    private static bool HasVisibleContent(ChatMessage message)
    {
        if (message.Contents.Count == 0)
        {
            return false;
        }

        foreach (var content in message.Contents)
        {
            // TextContent is visible
            if (content is TextContent textContent && !string.IsNullOrWhiteSpace(textContent.Text))
            {
                return true;
            }

            // Other content types that are not function calls/results are visible
            if (content is not FunctionCallContent && content is not FunctionResultContent)
            {
                return true;
            }
        }

        return false;
    }

    private static RenderFragment CreateRenderMessage(
        ChatMessage message,
        RenderFragment getRenderContents)
    {
        var roleClass = $"{message.Role}-message";
        return builder =>
        {
            // Check visibility at render time, not at template creation time
            // This is important because message contents may change during streaming
            if (!HasVisibleContent(message))
            {
                return; // Don't render messages without visible content
            }

            builder.OpenElement(0, "div");
            if (!string.IsNullOrEmpty(message.MessageId))
            {
                builder.AddAttribute(1, "id", message.MessageId);
            }
            builder.AddAttribute(2, "class", $"chat-message {roleClass}");
            builder.AddContent(3, getRenderContents);
            builder.CloseElement();
        };
    }
}
