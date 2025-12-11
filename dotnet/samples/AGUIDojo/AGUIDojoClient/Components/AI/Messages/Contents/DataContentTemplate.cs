// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

/// <summary>
/// Default template for rendering DataContent. Renders nothing by default
/// as DataContent typically contains binary/JSON data not meant for display.
/// </summary>
public class DataContentTemplate : ContentTemplateBase
{
    [CascadingParameter] internal MessageListContext Context { get; set; } = default!;

    public override void Attach(RenderHandle renderHandle)
    {
        this.ChildContent = this.RenderData;
    }

    public override Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);
        this.Context.RegisterContentTemplate(this);
        return Task.CompletedTask;
    }

    public override bool When(ContentContext context)
    {
        return context.Content is DataContent;
    }

    private RenderFragment RenderData(ContentContext content) => builder =>
    {
        // By default, render nothing.
    };
}
