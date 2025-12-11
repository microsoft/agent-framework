// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

/// <summary>
/// Default template for FunctionResultContent that renders nothing.
/// Function results are internal tool responses and typically don't need
/// visual representation in the chat UI.
/// </summary>
public class FunctionResultTemplate : ContentTemplateBase
{
    [CascadingParameter] internal MessageListContext Context { get; set; } = default!;

    public override void Attach(RenderHandle renderHandle)
    {
        // This component never renders anything by itself.
        this.ChildContent = this.RenderFunctionResult;
    }

    public override Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);
        this.Context.RegisterContentTemplate(this);
        return Task.CompletedTask;
    }

    /// <summary>
    /// Only match FunctionResultContent.
    /// </summary>
    public override bool When(ContentContext context) => context.Content is FunctionResultContent;

    private RenderFragment RenderFunctionResult(ContentContext content) => builder =>
    {
        // By default, function results are not rendered visually.
        // The result data is typically processed by the agent to generate text responses.
    };
}
