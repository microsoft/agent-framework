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
    public new bool When(ContentContext context)
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
        if (content.Content is FunctionCallContent call)
        {
            // Get or create the invocation context which tracks call and result
            var invocation = this.Context.GetOrCreateInvocation(call);

            builder.OpenComponent<CascadingValue<InvocationContext>>(0);
            builder.AddComponentParameter(1, "Value", invocation);
            builder.AddComponentParameter(2, "IsFixed", true);
            builder.AddComponentParameter(3, "ChildContent", (RenderFragment)(innerBuilder =>
            {
                // Default fallback rendering - shows function name and loading/result status
                innerBuilder.OpenElement(0, "div");
                innerBuilder.AddAttribute(1, "class", "function-call");
                innerBuilder.AddContent(2, $"Function: {call.Name}");
                if (invocation.HasResult)
                {
                    innerBuilder.AddContent(3, " [Result available]");
                }
                else
                {
                    innerBuilder.AddContent(3, " [Loading...]");
                }

                innerBuilder.CloseElement();
            }));
            builder.CloseComponent();
        }
    };
}
