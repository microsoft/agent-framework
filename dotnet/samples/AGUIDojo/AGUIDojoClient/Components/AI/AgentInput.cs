// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

public sealed partial class AgentInput : IComponent, IDisposable
{
    private RenderHandle _renderHandle;
    private AgentBoundaryContext<object?>? _context;
    private string? _inputText;
    private RunStatusSubscription? _subscription;

    [CascadingParameter] public AgentBoundaryContext<object?>? AgentContext { get; set; }

    [Parameter] public string Placeholder { get; set; } = "Type a message...";

    public void Attach(RenderHandle renderHandle)
    {
        this._renderHandle = renderHandle;
    }

    public Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);

        // Unsubscribe from previous context if it changed
        if (this._context != this.AgentContext)
        {
            this._subscription?.Dispose();
            this._context = this.AgentContext;

            // Subscribe to run status changes
            if (this._context != null)
            {
                this._subscription = this._context.SubscribeToRunStatusChanges(this.OnRunStatusChanged);
            }
        }

        this.Render();
        return Task.CompletedTask;
    }

    private void OnRunStatusChanged()
    {
        this.Render();
    }

    private void Render()
    {
        var isProcessing = this._context?.IsProcessing ?? false;
        var isDisabled = string.IsNullOrWhiteSpace(this._inputText) || isProcessing;

        this._renderHandle.Render(builder =>
        {
            builder.OpenElement(0, "div");
            builder.AddAttribute(1, "class", "agent-input");

            builder.OpenElement(2, "textarea");
            builder.AddAttribute(3, "value", this._inputText);
            builder.AddAttribute(4, "oninput", EventCallback.Factory.Create<ChangeEventArgs>(this, e => { this._inputText = e.Value?.ToString(); this.Render(); }));
            builder.AddAttribute(5, "placeholder", this.Placeholder);
            builder.AddAttribute(6, "rows", "1");
            builder.AddAttribute(7, "disabled", isProcessing);
            builder.CloseElement();

            builder.OpenElement(8, "button");
            builder.AddAttribute(9, "class", "send-button");
            builder.AddAttribute(10, "onclick", EventCallback.Factory.Create(this, this.SendAsync));
            builder.AddAttribute(11, "disabled", isDisabled);
            builder.AddMarkupContent(12, """<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>""");
            builder.CloseElement(); // close button

            builder.CloseElement(); // close div
        });
    }

    private async Task SendAsync()
    {
        if (!string.IsNullOrWhiteSpace(this._inputText) && this._context is { IsProcessing: false })
        {
            var text = this._inputText;
            this._inputText = ""; // Clear input immediately
            this.Render(); // Re-render to clear input

            await this._context.SendAsync(new ChatMessage(ChatRole.User, text));
        }
    }

    public void Dispose()
    {
        this._subscription?.Dispose();
    }
}
