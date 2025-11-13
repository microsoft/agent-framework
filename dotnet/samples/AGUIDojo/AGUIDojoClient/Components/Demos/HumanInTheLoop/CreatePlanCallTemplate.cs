// Copyright (c) Microsoft. All rights reserved.

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.AI;
using Microsoft.AspNetCore.Components.Rendering;
using Microsoft.Extensions.AI;

namespace AGUIDojoClient.Components.Demos.HumanInTheLoop;

/// <summary>
/// Template for rendering create_plan function call content.
/// The PlanCard will subscribe to events to track confirm_plan and update_plan_step calls.
/// </summary>
public class CreatePlanCallTemplate : ContentTemplateBase
{
    [CascadingParameter] internal MessageListContext Context { get; set; } = default!;

    public override void Attach(RenderHandle renderHandle)
    {
        // This component never renders anything by itself.
        this.ChildContent = this.RenderCreatePlanCall;
    }

    public override Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);
        this.Context.RegisterContentTemplate(this);
        return Task.CompletedTask;
    }

    /// <summary>
    /// Determines if this template should handle the given content.
    /// Matches FunctionCallContent for the create_plan function.
    /// </summary>
    public override bool When(ContentContext context)
    {
        // Only match FunctionCallContent for the create_plan function
        return context.Content is FunctionCallContent call &&
               string.Equals(call.Name, "create_plan", StringComparison.OrdinalIgnoreCase);
    }

    private RenderFragment RenderCreatePlanCall(ContentContext content) => builder =>
    {
        if (content.Content is FunctionCallContent call)
        {
            // Get the invocation context which tracks both call and result
            var invocation = this.Context.GetOrCreateInvocation(call);

            // Provide both the invocation context and message list context to PlanCard
            builder.OpenComponent<CascadingValue<InvocationContext>>(0);
            builder.AddComponentParameter(1, "Value", invocation);
            builder.AddComponentParameter(2, "IsFixed", true);
            builder.AddComponentParameter(3, "ChildContent", (RenderFragment)(innerBuilder =>
            {
                // Also cascade the MessageListContext so PlanCard can track other tool calls
                innerBuilder.OpenComponent<CascadingValue<MessageListContext>>(0);
                innerBuilder.AddComponentParameter(1, "Value", this.Context);
                innerBuilder.AddComponentParameter(2, "IsFixed", true);
                innerBuilder.AddComponentParameter(3, "ChildContent", (RenderFragment)(cardBuilder =>
                {
                    // Render the PlanCard component
                    cardBuilder.OpenComponent<PlanCard>(0);
                    cardBuilder.CloseComponent();
                }));
                innerBuilder.CloseComponent();
            }));
            builder.CloseComponent();
        }
    };
}
