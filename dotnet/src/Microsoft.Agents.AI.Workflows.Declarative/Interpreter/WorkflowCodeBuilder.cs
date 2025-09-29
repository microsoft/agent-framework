// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

namespace Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

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

        return template.TransformText().Trim();
    }

    public void Connect(IModeledAction source, IModeledAction target, string? condition)
    {
        Debug.WriteLine($"> CONNECT: {source.Id} => {target.Id}{(condition is null ? string.Empty : " (?)")}");

        this.HandelAction(source);
        this.HandelAction(target);

        this._edges.Add(new EdgeTemplate(source.Id, target.Id, condition).TransformText());
    }

    private void HandelAction(IModeledAction action)
    {
        // All templates are based on "CodeTemplate"
        if (action is not CodeTemplate template)
        {
            // Something has gone very wrong.
            throw new DeclarativeModelException($"Unable to generate code for: {action.GetType().Name}.");
        }

        if (this._actions.Add(action.Id))
        {
            switch (action)
            {
                case EmptyTemplate:
                case DefaultTemplate:
                    this._instances.Add(template.TransformText());
                    break;
                case ActionTemplate actionTemplate:
                    this._definitions.Add(template.TransformText());
                    this._instances.Add(new InstanceTemplate(action.Id, this._rootId, actionTemplate.UseAgentProvider).TransformText());
                    break;
                case RootTemplate:
                    this._definitions.Add(template.TransformText());
                    break;
            }
        }
    }
}
