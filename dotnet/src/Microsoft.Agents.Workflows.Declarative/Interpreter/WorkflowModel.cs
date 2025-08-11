// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.Immutable;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

/// <summary>
/// %%% COMMENT
/// </summary>
internal delegate void ScopeCompletionHandler(); // %%% ACTION ???

/// <summary>
/// Provides dynamic model for constructing a declarative workflow.
/// </summary>
internal sealed class WorkflowModel
{
    public WorkflowModel(ExecutorIsh rootStep)
    {
        this.RootNode = this.DefineNode(rootStep);
    }

    private ModelNode RootNode { get; }

    private Dictionary<string, ModelNode> Nodes { get; } = [];

    private List<ModelLink> Links { get; } = [];

    public int GetDepth(string? nodeId)
    {
        if (nodeId == null)
        {
            return 0;
        }

        if (!this.Nodes.TryGetValue(nodeId, out ModelNode? sourceNode))
        {
            throw new UnknownActionException($"Unresolved step: {nodeId}.");
        }

        return sourceNode.Depth;
    }

    public void AddNode(ExecutorIsh step, string parentId, Type? actionType = null, ScopeCompletionHandler? completionHandler = null)
    {
        if (!this.Nodes.TryGetValue(parentId, out ModelNode? parentNode))
        {
            throw new UnknownActionException($"Unresolved parent for {step.Id}: {parentId}.");
        }

        ModelNode stepNode = this.DefineNode(step, parentNode, actionType, completionHandler);

        parentNode.Children.Add(stepNode);
    }

    public void AddLinkFromPeer(string parentId, string targetId, Func<object?, bool>? condition = null)
    {
        if (!this.Nodes.TryGetValue(parentId, out ModelNode? parentNode))
        {
            throw new UnknownActionException($"Unresolved step: {parentId}.");
        }

        if (parentNode.Children.Count == 0)
        {
            throw new WorkflowBuilderException($"Cannot add a link from a node with no children: {parentId}.");
        }

        ModelNode sourceNode = parentNode.Children.Count == 1 ? parentNode : parentNode.Children[parentNode.Children.Count - 2];

        this.Links.Add(new ModelLink(sourceNode, targetId, condition));
    }

    public void AddLink(string sourceId, string targetId, Func<object?, bool>? condition = null)
    {
        if (!this.Nodes.TryGetValue(sourceId, out ModelNode? sourceNode))
        {
            throw new UnknownActionException($"Unresolved step: {sourceId}.");
        }

        this.Links.Add(new ModelLink(sourceNode, targetId, condition));
    }

    public void ConnectNodes(WorkflowBuilder workflowBuilder)
    {
        foreach (ModelNode node in this.Nodes.Values.ToImmutableArray())
        {
            node.CompletionHandler?.Invoke();
        }

        foreach (ModelLink link in this.Links)
        {
            if (!this.Nodes.TryGetValue(link.TargetId, out ModelNode? targetNode))
            {
                throw new WorkflowBuilderException($"Unresolved target for {link.Source.Id}: {link.TargetId}.");
            }

            Console.WriteLine($"> CONNECT: {link.Source.Id} => {link.TargetId}"); // %%% LOGGER

            workflowBuilder.AddEdge(link.Source.Step, targetNode.Step, link.Condition);
        }
    }

    private ModelNode DefineNode(ExecutorIsh step, ModelNode? parentNode = null, Type? actionType = null, ScopeCompletionHandler? completionHandler = null)
    {
        ModelNode stepNode = new(step, parentNode, actionType, completionHandler);

        this.Nodes[stepNode.Id] = stepNode;

        return stepNode;
    }

    internal string? LocateParent<TAction>(string? itemId)
    {
        if (string.IsNullOrEmpty(itemId))
        {
            return null;
        }

        while (itemId != null)
        {
            if (!this.Nodes.TryGetValue(itemId, out ModelNode? itemNode))
            {
                throw new UnknownActionException($"Unresolved child: {itemId}.");
            }

            if (itemNode.ActionType == typeof(TAction))
            {
                return itemNode.Id;
            }

            itemId = itemNode.Parent?.Id;
        }

        return null;
    }

    private sealed class ModelNode(ExecutorIsh step, ModelNode? parent = null, Type? actionType = null, ScopeCompletionHandler? completionHandler = null)
    {
        public string Id => step.Id;

        public ExecutorIsh Step => step;

        public ModelNode? Parent { get; } = parent;

        public List<ModelNode> Children { get; } = [];

        public int Depth => this.Parent?.Depth + 1 ?? 0;

        public Type? ActionType => actionType;

        public ScopeCompletionHandler? CompletionHandler => completionHandler;
    }

    private sealed record class ModelLink(ModelNode Source, string TargetId, Func<object?, bool>? Condition = null);
}
