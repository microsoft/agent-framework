// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Core;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class WorkflowElementWalker : BotElementWalker
{
    private readonly WorkflowActionVisitor _visitor;

    public WorkflowElementWalker(BotElement rootElement, WorkflowActionVisitor visitor)
    {
        this._visitor = visitor;
        this.Visit(rootElement);
        this.Workflow = this._visitor.Complete();
    }

    public Workflow<string> Workflow { get; }

    public override bool DefaultVisit(BotElement definition)
    {
        if (definition is DialogAction action)
        {
            action.Accept(this._visitor);
        }

        return true;
    }
}
