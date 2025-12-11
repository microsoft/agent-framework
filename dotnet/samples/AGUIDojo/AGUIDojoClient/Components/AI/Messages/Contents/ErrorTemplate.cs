// Copyright (c) Microsoft. All rights reserved.

using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

/// <summary>
/// Default template for rendering ErrorContent. Renders nothing by default
/// to prevent the error from crashing the UI. More specific templates can
/// override this to display error messages.
/// </summary>
public class ErrorTemplate : ContentTemplateBase
{
    [CascadingParameter] internal MessageListContext Context { get; set; } = default!;

    public override void Attach(RenderHandle renderHandle)
    {
        this.ChildContent = this.RenderError;
    }

    public override Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);
        this.Context.RegisterContentTemplate(this);
        return Task.CompletedTask;
    }

    /// <summary>
    /// Determines if this template should handle the given content.
    /// Matches ErrorContent.
    /// </summary>
    public override bool When(ContentContext context)
    {
        return context.Content is ErrorContent;
    }

    private RenderFragment RenderError(ContentContext content) => builder =>
    {
        // By default, render nothing.
        // Specific templates can override to display error messages.
    };
}
