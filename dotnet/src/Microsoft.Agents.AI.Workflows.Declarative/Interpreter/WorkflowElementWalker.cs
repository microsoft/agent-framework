// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;

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

            if (action is Foreach foreachAction && ForeachExecutionOptions.Parse(foreachAction).IsParallel)
            {
                return false;
            }
        }

        return true;
    }
}
