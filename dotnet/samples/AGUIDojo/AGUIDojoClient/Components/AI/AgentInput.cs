// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

public partial class AgentInput : IComponent
{
    private RenderHandle _renderHandle;
    private AgentBoundaryContext<object?>? _context;
    private string? _inputText;

    [CascadingParameter] public AgentBoundaryContext<object?>? AgentContext { get; set; }

    [Inject] private ILogger<AgentInput> Logger { get; set; } = default!;

    [Parameter] public string Placeholder { get; set; } = "Type a message...";

    public void Attach(RenderHandle renderHandle)
    {
        this._renderHandle = renderHandle;
    }

    public Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);
        this._context = this.AgentContext;
        Log.AgentInputAttached(this.Logger);
        this.Render();
        return Task.CompletedTask;
    }

    private void Render()
    {
        Log.AgentInputRendering(this.Logger);
        this._renderHandle.Render(builder =>
        {
            builder.OpenElement(0, "div");
            builder.AddAttribute(1, "class", "agent-input");

            builder.OpenElement(2, "textarea");
            builder.AddAttribute(3, "value", this._inputText);
            builder.AddAttribute(4, "oninput", EventCallback.Factory.Create<ChangeEventArgs>(this, e => { this._inputText = e.Value?.ToString(); this.Render(); }));
            builder.AddAttribute(5, "placeholder", this.Placeholder);
            builder.AddAttribute(6, "rows", "1");
            builder.CloseElement();

            builder.OpenElement(7, "button");
            builder.AddAttribute(8, "class", "send-button");
            builder.AddAttribute(9, "onclick", EventCallback.Factory.Create(this, this.SendAsync));
            builder.AddAttribute(10, "disabled", string.IsNullOrWhiteSpace(this._inputText));
            builder.AddMarkupContent(11, """<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>""");
            builder.CloseElement(); // close button

            builder.CloseElement(); // close div
        });
    }

    private async Task SendAsync()
    {
        if (!string.IsNullOrWhiteSpace(this._inputText) && this._context != null)
        {
            var text = this._inputText;
            Log.AgentInputSendingMessage(this.Logger, text.Length);
            this._inputText = ""; // Clear input immediately
            this.Render(); // Re-render to clear input

            await this._context.SendAsync(new ChatMessage(ChatRole.User, text));
            Log.AgentInputMessageSent(this.Logger);
        }
    }

    private static partial class Log
    {
        [LoggerMessage(Level = LogLevel.Debug, Message = "AgentInput attached to render handle")]
        public static partial void AgentInputAttached(ILogger logger);

        [LoggerMessage(Level = LogLevel.Debug, Message = "AgentInput rendering")]
        public static partial void AgentInputRendering(ILogger logger);

        [LoggerMessage(Level = LogLevel.Debug, Message = "AgentInput sending message: {MessageLength} characters")]
        public static partial void AgentInputSendingMessage(ILogger logger, int messageLength);

        [LoggerMessage(Level = LogLevel.Debug, Message = "AgentInput message sent successfully")]
        public static partial void AgentInputMessageSent(ILogger logger);
    }
}
