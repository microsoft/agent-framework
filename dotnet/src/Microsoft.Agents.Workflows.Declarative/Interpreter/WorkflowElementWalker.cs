// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class WorkflowElementWalker : BotElementWalker
{
    static WorkflowElementWalker()
    {
        ProductContext.SetContext(Product.Foundry);
    }

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
