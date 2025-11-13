// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

public abstract class MessageTemplateBase : IComponent
{
    [CascadingParameter] internal MessageListContext Context { get; set; } = default!;

    public abstract bool When(MessageContext context);

    [Parameter] public RenderFragment<MessageContext> ChildContent { get; set; } = (message) => builder => { };

    public void Attach(RenderHandle renderHandle)
    {
    }

    public Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);
        this.Context.RegisterTemplate(this);
        return Task.CompletedTask;
    }

    internal RenderFragment? GetContentTemplate(AIContent content)
    {
        return this.Context.GetContentTemplate(content);
    }
}
