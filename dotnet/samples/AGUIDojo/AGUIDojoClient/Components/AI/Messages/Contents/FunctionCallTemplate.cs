// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

/// <summary>
/// Template for rendering function/tool call content in messages.
/// Provides access to both the call and its result (when available) via InvocationContext.
/// </summary>
public class FunctionCallTemplate : ContentTemplateBase
{
    /// <summary>
    /// Gets or sets the tool name to filter on. If null, matches all function calls.
    /// </summary>
    [Parameter] public string? ToolName { get; set; }

    [CascadingParameter] internal MessageListContext Context { get; set; } = default!;

    public override void Attach(RenderHandle renderHandle)
    {
        // This component never renders anything by itself.
        this.ChildContent = this.RenderFunctionCall;
    }

    public override Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);
        this.Context.RegisterContentTemplate(this);
        return Task.CompletedTask;
    }

    /// <summary>
    /// Determines if this template should handle the given content.
    /// </summary>
    /// <param name="context">The content context.</param>
    /// <returns>True if this template should render the content.</returns>
    public override bool When(ContentContext context)
    {
        if (context.Content is not FunctionCallContent call)
        {
            return false;
        }

        // Filter by tool name if specified
        if (this.ToolName != null && !string.Equals(call.Name, this.ToolName, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        return true;
    }

    private RenderFragment RenderFunctionCall(ContentContext content) => builder =>
    {
        // By default, function calls are not rendered visually.
        // Custom templates (like WeatherCallTemplate) can override this
        // behavior for specific functions by registering before this template.
    };
}
