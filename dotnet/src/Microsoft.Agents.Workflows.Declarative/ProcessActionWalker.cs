// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Core;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative;

internal sealed class ProcessActionWalker : BotElementWalker
{
    private readonly ProcessActionVisitor _visitor;

    public ProcessActionWalker(BotElement rootElement, ProcessActionVisitor visitor)
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
