// Copyright (c) Microsoft. All rights reserved.

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.AI;
using Microsoft.AspNetCore.Components.Rendering;
using Microsoft.Extensions.AI;

namespace AGUIDojoClient.Components.Demos.ToolBasedGenerativeUI;

/// <summary>
/// Template for rendering generate_haiku function call content.
/// Renders a HaikuCard component inline in the chat messages.
/// </summary>
public class HaikuCallTemplate : ContentTemplateBase
{
    [CascadingParameter] internal MessageListContext Context { get; set; } = default!;

    public override void Attach(RenderHandle renderHandle)
    {
        // This component never renders anything by itself.
        this.ChildContent = this.RenderHaikuCall;
    }

    public override Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);
        this.Context.RegisterContentTemplate(this);
        return Task.CompletedTask;
    }

    /// <summary>
    /// Determines if this template should handle the given content.
    /// Matches FunctionCallContent for the generate_haiku function.
    /// </summary>
    public override bool When(ContentContext context)
    {
        // Only match FunctionCallContent for the generate_haiku function
        return context.Content is FunctionCallContent call &&
               string.Equals(call.Name, "generate_haiku", StringComparison.OrdinalIgnoreCase);
    }

    private RenderFragment RenderHaikuCall(ContentContext content) => builder =>
    {
        if (content.Content is FunctionCallContent call)
        {
            // Get the invocation context which tracks both call and result
            var invocation = this.Context.GetOrCreateInvocation(call);

            // Provide the invocation context to child components
            builder.OpenComponent<CascadingValue<InvocationContext>>(0);
            builder.AddComponentParameter(1, "Value", invocation);
            builder.AddComponentParameter(2, "IsFixed", true);
            builder.AddComponentParameter(3, "ChildContent", (RenderFragment)(innerBuilder =>
            {
                // Render the HaikuCard component which uses InvocationContext
                innerBuilder.OpenComponent<HaikuCard>(0);
                innerBuilder.CloseComponent();
            }));
            builder.CloseComponent();
        }
    };
}
