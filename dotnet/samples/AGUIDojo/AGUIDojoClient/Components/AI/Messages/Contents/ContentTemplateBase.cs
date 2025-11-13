// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.AspNetCore.Components.AI;

public abstract class ContentTemplateBase : IComponent
{
    public abstract void Attach(RenderHandle renderHandle);

    public abstract Task SetParametersAsync(ParameterView parameters);

    public virtual bool When(ContentContext context) => true;

    [Parameter] public RenderFragment<ContentContext> ChildContent { get; set; } = (content) => builder => { };
}
