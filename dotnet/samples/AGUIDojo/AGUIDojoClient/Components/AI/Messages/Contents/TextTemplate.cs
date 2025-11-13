// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

public class TextTemplate : ContentTemplateBase
{
    [CascadingParameter] internal MessageListContext Context { get; set; } = default!;

    public override void Attach(RenderHandle renderHandle)
    {
        // This component never renders anything by itself.
        this.ChildContent = this.RenderText;
    }

    public override Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);
        this.Context.RegisterContentTemplate(this);
        return Task.CompletedTask;
    }

    private RenderFragment RenderText(ContentContext content) => builder =>
    {
        if (content.Content is TextContent textContent)
        {
            builder.AddContent(0, textContent.Text);
        }
    };
}
