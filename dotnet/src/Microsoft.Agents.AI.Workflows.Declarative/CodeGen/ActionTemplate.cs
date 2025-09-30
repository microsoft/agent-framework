// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal abstract class ActionTemplate : CodeTemplate, IModeledAction
{
    public string Id { get; private set; } = string.Empty;

    public string Name { get; private set; } = string.Empty;

    public string ParentId { get; private set; } = string.Empty;

    public bool UseAgentProvider { get; init; }

    protected TAction Initialize<TAction>(TAction model) where TAction : DialogAction
    {
        this.Id = model.GetId();
        this.ParentId = model.GetParentId() ?? WorkflowActionVisitor.Steps.Root();
        this.Name = this.Id.FormatType();

        return model;
    }
}
