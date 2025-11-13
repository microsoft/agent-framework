// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

public class MessageContext
{
    private readonly MessageListContext _messageListContext;
    private RenderFragment? _contentsRenderer;
    private MessageTemplateBase? _template;
    private readonly Dictionary<AIContent, RenderFragment> _contentRenderers = [];

    internal MessageContext(ChatMessage message, MessageListContext messageListContext)
    {
        this.ChatMessage = message;
        this._messageListContext = messageListContext;
    }

    public ChatMessage? ChatMessage { get; init; }

    public IList<ChatResponseUpdate>? ResponseUpdates { get; init; }

    public RenderFragment RenderContents() => this.GetOrCreateContentsRenderer();

    internal void SetTemplate(MessageTemplateBase template)
    {
        this._template = template;
    }

    private RenderFragment GetOrCreateContentsRenderer()
    {
        if (this._contentsRenderer != null)
        {
            return this._contentsRenderer;
        }

        if (this._template == null)
        {
            throw new InvalidOperationException("Message template has not been set for this message context.");
        }

        this._contentsRenderer = builder =>
        {
            if (this.ChatMessage != null)
            {
                for (int i = 0; i < this.ChatMessage.Contents.Count; i++)
                {
                    var content = this.ChatMessage.Contents[i];
                    builder.AddContent(0, this.ResolveContentRenderer(content));
                }
            }
            else if (this.ResponseUpdates != null)
            {
                for (int i = 0; i < this.ResponseUpdates.Count; i++)
                {
                    var update = this.ResponseUpdates[i];
                    for (int j = 0; j < update.Contents.Count; j++)
                    {
                        var content = update.Contents[j];
                        if (this._contentRenderers.TryGetValue(content, out var contentRenderer))
                        {
                            builder.AddContent(0, contentRenderer);
                        }
                    }
                }
            }
            else
            {
                throw new InvalidOperationException("MessageContext must have either a ChatMessage or ResponseUpdates to render contents.");
            }
        };

        return this._contentsRenderer;
    }

    private RenderFragment ResolveContentRenderer(AIContent content)
    {
        if (this._contentRenderers.TryGetValue(content, out var contentRenderer))
        {
            return contentRenderer;
        }

        Debug.Assert(this._template != null);
        contentRenderer = this._template.GetContentTemplate(content);
        if (contentRenderer != null)
        {
            this._contentRenderers[content] = contentRenderer;
            return contentRenderer;
        }
        contentRenderer = this._messageListContext.GetContentTemplate(content);
        this._contentRenderers[content] = contentRenderer;
        return contentRenderer;
    }
}
