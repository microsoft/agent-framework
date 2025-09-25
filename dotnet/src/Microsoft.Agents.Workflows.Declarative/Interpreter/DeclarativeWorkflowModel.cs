// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

/// <summary>
/// Provides dynamic model for constructing a declarative workflow.
/// </summary>
internal sealed class DeclarativeWorkflowModel
{
    public DeclarativeWorkflowModel(Executor rootStep)
    {
        this.DefineNode(rootStep);
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

    public void AddNode(Executor executor, string parentId, Action? completionHandler = null)
    {
        if (!this.Nodes.TryGetValue(parentId, out ModelNode? parentNode))
        {
            throw new DeclarativeModelException($"Unresolved parent for {executor.Id}: {parentId}.");
        }

        ModelNode stepNode = this.DefineNode(executor, parentNode, completionHandler);

        parentNode.Children.Add(stepNode);
    }

    public void AddPort(InputPort port, string parentId)
    {
        if (!this.Nodes.TryGetValue(parentId, out ModelNode? parentNode))
        {
            throw new DeclarativeModelException($"Unresolved parent for {port.Id}: {parentId}.");
        }

        ModelNode stepNode = this.DefineNode(port, parentNode);

        parentNode.Children.Add(stepNode);
    }

    public void AddLinkFromPeer(string parentId, string targetId, Func<object?, bool>? condition = null)
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

    public void AddLink(string sourceId, string targetId, Func<object?, bool>? condition = null)
    {
        if (!this.Nodes.TryGetValue(sourceId, out ModelNode? sourceNode))
        {
            throw new DeclarativeModelException($"Unresolved step: {sourceId}.");
        }

        this.Links.Add(new ModelLink(sourceNode, targetId, condition));
    }

    public void ConnectNodes(WorkflowBuilder workflowBuilder)
    {
        // Push `Values` into array to avoid modification during iteration.
        foreach (ModelNode node in this.Nodes.Values.ToArray())
        {
            if (node.CompletionHandler is not null)
            {
                Debug.WriteLine($"> CLOSE: {node.Id} (x{node.Children.Count})");

                node.CompletionHandler.Invoke();
            }
        }

        foreach (ModelLink link in this.Links)
        {
            if (!this.Nodes.TryGetValue(link.TargetId, out ModelNode? targetNode))
            {
                throw new DeclarativeModelException($"Unresolved target for {link.Source.Id}: {link.TargetId}.");
            }

            Debug.WriteLine($"> CONNECT: {link.Source.Id} => {link.TargetId}{(link.Condition is null ? string.Empty : " (?)")}");

            workflowBuilder.AddEdge(GetExecutorIsh(link.Source), GetExecutorIsh(targetNode), link.Condition);
        }

        static ExecutorIsh GetExecutorIsh(ModelNode node) => node.Port ?? (ExecutorIsh)node.Executor;
    }

    private ModelNode DefineNode(Executor executor, ModelNode? parentNode = null, Action? completionHandler = null)
    {
        ModelNode stepNode = new(executor, port: null, parentNode, completionHandler);

        this.Nodes.Add(stepNode.Id, stepNode);

        return stepNode;
    }

    private ModelNode DefineNode(InputPort port, ModelNode? parentNode = null)
    {
        ModelNode stepNode = new(executor: null!, port, parentNode);

        this.Nodes.Add(stepNode.Id, stepNode);

        return stepNode;
    }

    internal TAction? LocateParent<TAction>(string? itemId) where TAction : Executor
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

            if (itemNode.ExecutorType == typeof(TAction))
            {
                return (TAction)itemNode.Executor;
            }

            itemId = itemNode.Parent?.Id;
        }

        return null;
    }

    private sealed class ModelNode(Executor executor, InputPort? port, ModelNode? parent = null, Action? completionHandler = null)
    {
        public string Id => port?.Id ?? executor.Id;

        public Executor Executor => executor;

        public InputPort? Port => port;

        public Type? ExecutorType => this.Port?.GetType() ?? this.Executor.GetType();

        public ModelNode? Parent { get; } = parent;

        public List<ModelNode> Children { get; } = [];

        public int Depth => (this.Parent?.Depth + 1) ?? 0;

        public Action? CompletionHandler => completionHandler;
    }

    private sealed record class ModelLink(ModelNode Source, string TargetId, Func<object?, bool>? Condition = null);
}
