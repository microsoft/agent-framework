// Copyright (c) Microsoft. All rights reserved.

using Microsoft.AspNetCore.Components.Rendering;

namespace Microsoft.AspNetCore.Components.AI;

#pragma warning disable CA1812 // Internal class is apparently never instantiated
internal sealed class ContentBlock : IComponent
#pragma warning restore CA1812 // Internal class is apparently never instantiated
{
    private RenderHandle _renderHandle;

    [Parameter] public RenderFragment ChildContent { get; set; } = default!;

    public void Attach(RenderHandle renderHandle)
    {
        this._renderHandle = renderHandle;
    }

    public Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);
        // Always render when parameters are set - the parent component (MessageList)
        // only triggers renders when there are actual updates to show.
        this._renderHandle.Render(this.Render);
        return Task.CompletedTask;
    }

    private void Render(RenderTreeBuilder builder)
    {
        builder.AddContent(0, this.ChildContent);
    }
}
