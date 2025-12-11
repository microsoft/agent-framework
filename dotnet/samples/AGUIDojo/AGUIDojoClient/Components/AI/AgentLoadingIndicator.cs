// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.AspNetCore.Components.AI;

/// <summary>
/// A component that displays a loading indicator (three animated dots) when the agent is processing.
/// </summary>
public sealed partial class AgentLoadingIndicator : IComponent, IDisposable
{
    private RenderHandle _renderHandle;
    private AgentBoundaryContext<object?>? _context;
    private RunStatusSubscription? _subscription;

    [CascadingParameter] public AgentBoundaryContext<object?>? AgentContext { get; set; }

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

        this._renderHandle.Render(builder =>
        {
            if (!isProcessing)
            {
                return;
            }

            builder.OpenElement(0, "div");
            builder.AddAttribute(1, "class", "agent-loading-indicator");
            builder.OpenElement(2, "div");
            builder.AddAttribute(3, "class", "agent-loading-dots");
            builder.AddMarkupContent(4, "<span></span><span></span><span></span>");
            builder.CloseElement();
            builder.CloseElement();
        });
    }

    public void Dispose()
    {
        this._subscription?.Dispose();
    }
}
