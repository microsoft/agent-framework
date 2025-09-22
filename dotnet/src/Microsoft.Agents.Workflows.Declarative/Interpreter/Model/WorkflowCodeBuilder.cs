// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using Microsoft.Agents.Workflows.Declarative.CodeGen;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class WorkflowCodeBuilder : IModelBuilder<string>
{
    private readonly HashSet<string> _actions;
    private readonly List<string> _definitions;
    private readonly List<string> _instances;
    private readonly List<string> _edges;
    private readonly string _rootId;

    public WorkflowCodeBuilder(string rootId)
    {
        this._actions = [];
        this._definitions = [];
        this._instances = [];
        this._edges = [];
        this._rootId = rootId;
    }

    public string GenerateCode(string? workflowNamespace, string? workflowPrefix)
    {
        ProviderTemplate template =
            new(this._rootId, this._definitions, this._instances, this._edges)
            {
                Namespace = workflowNamespace,
                Prefix = workflowPrefix,
            };

        return template.TransformText();
    }

    public void Connect(IModeledAction source, IModeledAction target, string? condition)
    {
        Debug.WriteLine($"> CONNECT: {source.Id} => {target.Id}{(condition is null ? string.Empty : " (?)")}");

        this.HandelAction(source);
        this.HandelAction(target);

        this._edges.Add(new EdgeTemplate(source.Id, target.Id).TransformText()); // %%% WITH CONDITION
    }

    private void HandelAction(IModeledAction action)
    {
        if (action is not CodeTemplate template)
        {
            throw new DeclarativeModelException($"Unable to generate code for: {action.GetType().Name}.");
        }

        if (this._actions.Add(action.Id))
        {
            this._definitions.Add(template.TransformText());

            if (action is not RootTemplate)
            {
                this._instances.Add(new InstanceTemplate(action.Id, this._rootId).TransformText()); // %%% WITH PROVIDER, OR NOT ???
            }
        }
    }
}