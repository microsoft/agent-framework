// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

internal sealed class WorkflowElementWalker : BotElementWalker
{
    private readonly DialogActionVisitor _visitor;

    public WorkflowElementWalker(DialogActionVisitor visitor)
    {
        this._visitor = visitor;
    }

    public override bool DefaultVisit(BotElement definition)
    {
        if (definition is DialogAction action)
        {
            action.Accept(this._visitor);
        }

        return true;
    }
}
