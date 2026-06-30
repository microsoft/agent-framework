// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;

namespace Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

internal interface IModeledAction
{
    string Id { get; }
}

internal interface IModelBuilder<TCondition> where TCondition : class
{
    void Connect(IModeledAction source, IModeledAction target, TCondition? condition = null);
}

internal sealed class WorkflowModel<TCondition> where TCondition : class
{
    public WorkflowModel(IModeledAction rootAction)
    {
        this.DefineNode(rootAction);
    }

    private Dictionary<string, ModelNode> Nodes { get; } = [];

    private List<ModelLink> Links { get; } = [];

    public int GetDepth(string? nodeId)
    {
        if (nodeId is null)
        {
            return 0;
        }

        if (!this.Nodes.TryGetValue(nodeId, out ModelNode? sourceNode))
        {
            throw new DeclarativeModelException($"Unresolved step: {nodeId}.");
        }

        return sourceNode.Depth;
    }

    public void AddNode(IModeledAction action, string parentId, Action? completionHandler = null)
    {
        if (!this.Nodes.TryGetValue(parentId, out ModelNode? parentNode))
        {
            throw new DeclarativeModelException($"Unresolved parent for {action.Id}: {parentId}.");
        }

        ModelNode stepNode = this.DefineNode(action, parentNode, completionHandler);

        parentNode.Children.Add(stepNode);
    }

    public void AddLinkFromPeer(string parentId, string targetId, TCondition? condition = null)
    {
        if (!this.Nodes.TryGetValue(parentId, out ModelNode? parentNode))
        {
            throw new DeclarativeModelException($"Unresolved step: {parentId}.");
        }

        if (parentNode.Children.Count == 0)
        {
            throw new DeclarativeModelException($"Cannot add a link from a node with no children: {parentId}.");
        }

        ModelNode sourceNode = parentNode.Children.Count == 1 ? parentNode : parentNode.Children[parentNode.Children.Count - 2];

        this.Links.Add(new ModelLink(sourceNode, targetId, condition));
    }

    public void AddLink(string sourceId, string targetId, TCondition? condition = null)
    {
        if (!this.Nodes.TryGetValue(sourceId, out ModelNode? sourceNode))
        {
            throw new DeclarativeModelException($"Unresolved step: {sourceId}.");
        }

        this.Links.Add(new ModelLink(sourceNode, targetId, condition));
    }

    public void Build(IModelBuilder<TCondition> builder)
    {
        // Push into array to avoid modification during iteration.
        foreach (ModelNode node in this.Nodes.Values.ToArray())
        {
            if (node.CompletionHandler is not null)
            {
                Debug.WriteLine($"> CLOSE: {node.Action.Id} (x{node.Children.Count})");

                node.CompletionHandler.Invoke();
            }
        }

        foreach (ModelLink link in this.Links)
        {
            if (!this.Nodes.TryGetValue(link.TargetId, out ModelNode? targetNode))
            {
                throw new DeclarativeModelException($"Unresolved target for {link.Source.Action.Id}: {link.TargetId}.");
            }

            builder.Connect(link.Source.Action, targetNode.Action, link.Condition);
        }
    }

    private ModelNode DefineNode(IModeledAction action, ModelNode? parentNode = null, Action? completionHandler = null)
    {
        ModelNode newNode = new(action, parentNode, completionHandler);

        this.Nodes.Add(action.Id, newNode);

        return newNode;
    }

    public TAction? LocateParent<TAction>(string? itemId) where TAction : class, IModeledAction
    {
        if (string.IsNullOrEmpty(itemId))
        {
            return null;
        }

        while (itemId is not null)
        {
            if (!this.Nodes.TryGetValue(itemId, out ModelNode? itemNode))
            {
                throw new DeclarativeModelException($"Unresolved child: {itemId}.");
            }

            if (itemNode.Action.GetType() == typeof(TAction))
            {
                return (TAction)itemNode.Action;
            }

            itemId = itemNode.Parent?.Action.Id;
        }

        return null;
    }

    /// <summary>
    /// Finds all non-discrete parent actions that need completion events raised.
    /// These are actions that rely on their Post step to raise completion events
    /// (e.g., ConditionGroupExecutor, ForeachExecutor).
    /// </summary>
    public IEnumerable<TAction> LocateNonDiscreteAncestors<TAction>(string? itemId) where TAction : class, IModeledAction
    {
        if (string.IsNullOrEmpty(itemId))
        {
            yield break;
        }

        // Get the starting node and move to its parent first (don't include the starting node)
        if (!this.Nodes.TryGetValue(itemId, out ModelNode? startNode))
        {
            yield break;
        }

        string? currentId = startNode.Parent?.Action.Id;

        while (currentId is not null)
        {
            if (!this.Nodes.TryGetValue(currentId, out ModelNode? itemNode))
            {
                yield break;
            }

            // Check if this is a non-discrete action type that needs completion events
            // (actions that rely on Post step for completion, not HandleAsync finally block)
            if (itemNode.Action is TAction nonDiscreteAction)
            {
                Type actionType = nonDiscreteAction.GetType();
                Type? baseType = actionType.BaseType;

                // ConditionGroupExecutor and ForeachExecutor are non-discrete
                // They have IsDiscreteAction = false and raise completion in their Post step
                bool isNonDiscrete = actionType.Name.Contains("ConditionGroupExecutor") ||
                                    actionType.Name.Contains("ForeachExecutor") ||
                                    (baseType is not null && (baseType.Name.Contains("ConditionGroupExecutor") ||
                                                            baseType.Name.Contains("ForeachExecutor")));

                if (isNonDiscrete)
                {
                    yield return nonDiscreteAction;
                }
            }

            currentId = itemNode.Parent?.Action.Id;
        }
    }

    private sealed class ModelNode(IModeledAction action, ModelNode? parent = null, Action? completionHandler = null)
    {
        public IModeledAction Action => action;

        public ModelNode? Parent { get; } = parent;

        public List<ModelNode> Children { get; } = [];

        public int Depth => (this.Parent?.Depth + 1) ?? 0;

        public Action? CompletionHandler => completionHandler;
    }

    private sealed record class ModelLink(ModelNode Source, string TargetId, TCondition? Condition = null);
}
