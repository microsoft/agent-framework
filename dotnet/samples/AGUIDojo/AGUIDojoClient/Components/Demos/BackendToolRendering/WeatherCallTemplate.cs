// Copyright (c) Microsoft. All rights reserved.

using AGUIDojoClient.Components.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

/// <summary>
/// Template for rendering weather function call content with its result.
/// Uses InvocationContext to access both the call arguments and result.
/// </summary>
public class WeatherCallTemplate : ContentTemplateBase
{
    [CascadingParameter] internal MessageListContext Context { get; set; } = default!;

    public override void Attach(RenderHandle renderHandle)
    {
        // This component never renders anything by itself.
        this.ChildContent = this.RenderWeatherCall;
    }

    public override Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);
        this.Context.RegisterContentTemplate(this);
        return Task.CompletedTask;
    }

    /// <summary>
    /// Determines if this template should handle the given content.
    /// Matches FunctionCallContent for the get_weather function.
    /// </summary>
    public new bool When(ContentContext context)
    {
        // Only match FunctionCallContent for the get_weather function
        return context.Content is FunctionCallContent call &&
               string.Equals(call.Name, "get_weather", StringComparison.OrdinalIgnoreCase);
    }

    private RenderFragment RenderWeatherCall(ContentContext content) => builder =>
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
                // Render the WeatherCard component which uses InvocationContext
                innerBuilder.OpenComponent<AGUIDojoClient.Components.Demos.BackendToolRendering.WeatherCard>(0);
                innerBuilder.CloseComponent();
            }));
            builder.CloseComponent();
        }
    };
}
