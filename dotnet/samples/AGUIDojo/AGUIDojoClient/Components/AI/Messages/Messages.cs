// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.AspNetCore.Components.Rendering;

namespace Microsoft.AspNetCore.Components.AI;

public partial class Messages : IComponent
{
    private RenderHandle _renderHandle;
    private RenderFragment? _renderContents;

    private IAgentBoundaryContext? _context;
    private MessageListContext? _messageListContext;

    [CascadingParameter] public IAgentBoundaryContext? AgentContext { get; set; }

    [Parameter]
    public RenderFragment MessageTemplates { get; set; } = builder =>
    {
        builder.OpenComponent<DefaultMessageTemplate>(0);
        builder.CloseComponent();
    };

    [Parameter]
    public RenderFragment ContentTemplates { get; set; } = builder =>
    {
        builder.OpenComponent<TextTemplate>(0);
        builder.CloseComponent();
    };

    public void Attach(RenderHandle renderHandle)
    {
        this._renderHandle = renderHandle;
        this._renderContents = this.RenderContents;
    }

    public Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);

        if (this.AgentContext == null)
        {
            throw new InvalidOperationException("Messages component must be used within an AgentBoundary.");
        }

        if (this._context != null && this.AgentContext != this._context)
        {
            throw new InvalidOperationException("Messages component cannot change AgentBoundaryContext.");
        }

        this._context = this.AgentContext;

        if (this._messageListContext == null)
        {
            Log.MessagesAttached(this._context.Logger);
            this._messageListContext = new MessageListContext(this.AgentContext);
            Log.MessagesInitialized(this._context.Logger);
            this.Render();
        }

        return Task.CompletedTask;
    }

    private void Render()
    {
        Log.MessagesRendering(this._context?.Logger!);
        this._renderHandle.Render(this.RenderCore);
    }

    private void RenderCore(RenderTreeBuilder builder)
    {
        builder.OpenComponent<CascadingValue<MessageListContext>>(0);
        builder.AddComponentParameter(1, "Value", this._messageListContext);
        builder.AddComponentParameter(2, "IsFixed", true);
        builder.AddComponentParameter(3, "ChildContent", this._renderContents);
        builder.CloseComponent();
    }

    private void RenderContents(RenderTreeBuilder builder)
    {
        Debug.Assert(this._messageListContext != null);
        this._messageListContext.BeginCollectingTemplates();
        builder.AddContent(1, this.MessageTemplates);
        builder.AddContent(2, this.ContentTemplates);
        builder.OpenComponent<MessageList>(3);
        builder.CloseComponent();
    }

    private static partial class Log
    {
        [LoggerMessage(Level = LogLevel.Debug, Message = "Messages component attached to render handle")]
        public static partial void MessagesAttached(ILogger logger);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Messages component initialized with MessageListContext")]
        public static partial void MessagesInitialized(ILogger logger);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Messages component rendering")]
        public static partial void MessagesRendering(ILogger logger);
    }
}
