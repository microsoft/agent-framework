// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Provides builder patterns for constructing a declarative process workflow.
/// </summary>
internal sealed class ProcessWorkflowBuilder
{
    public ProcessWorkflowBuilder(ExecutorIsh rootStep)
    {
        this.RootNode = this.DefineNode(rootStep);
    }

    private ProcessWorkflowNode RootNode { get; }

    private Dictionary<string, ProcessWorkflowNode> Steps { get; } = [];

    private List<ProcessWorkflowLink> Links { get; } = [];

    public int GetDepth(string? nodeId)
    {
        if (nodeId == null)
        {
            return 0;
        }

        if (!this.Steps.TryGetValue(nodeId, out ProcessWorkflowNode? sourceNode))
        {
            throw new UnknownActionException($"Unresolved step: {nodeId}.");
        }

        return sourceNode.Depth;
    }

    public void AddNode(ExecutorIsh step, string parentId, Type? actionType = null)
    {
        if (!this.Steps.TryGetValue(parentId, out ProcessWorkflowNode? parentNode))
        {
            throw new UnknownActionException($"Unresolved parent for {step.Id}: {parentId}.");
        }

        ProcessWorkflowNode stepNode = this.DefineNode(step, parentNode, actionType);

        parentNode.Children.Add(stepNode);
    }

    public void AddLinkFromPeer(string parentId, string targetId, Func<object?, bool>? condition = null)
    {
        if (!this.Steps.TryGetValue(parentId, out ProcessWorkflowNode? parentNode))
        {
            throw new UnknownActionException($"Unresolved step: {parentId}.");
        }

        if (parentNode.Children.Count == 0)
        {
            throw new WorkflowBuilderException($"Cannot add a link from a node with no children: {parentId}.");
        }

        ProcessWorkflowNode sourceNode = parentNode.Children.Count == 1 ? parentNode : parentNode.Children[parentNode.Children.Count - 2];

        this.Links.Add(new ProcessWorkflowLink(sourceNode, targetId, condition));
    }

    public void AddLink(string sourceId, string targetId, Func<object?, bool>? condition = null)
    {
        if (!this.Steps.TryGetValue(sourceId, out ProcessWorkflowNode? sourceNode))
        {
            throw new UnknownActionException($"Unresolved step: {sourceId}.");
        }

        this.Links.Add(new ProcessWorkflowLink(sourceNode, targetId, condition));
    }

    //public void AddStop(string nodeId) // %%% REMOVE
    //{
    //    if (!this.Steps.TryGetValue(nodeId, out ProcessWorkflowNode? sourceNode))
    //    {
    //        throw new UnknownActionException($"Unresolved node: {nodeId}.");
    //    }

    //    sourceNode.Step.OnFunctionResult(KernelDelegateProcessStep.FunctionName).StopProcess();
    //}

    public void ConnectNodes(WorkflowBuilder workflowBuilder)
    {
        foreach (ProcessWorkflowLink link in this.Links)
        {
            if (!this.Steps.TryGetValue(link.TargetId, out ProcessWorkflowNode? targetNode))
            {
                throw new WorkflowBuilderException($"Unresolved target for {link.Source.Id}: {link.TargetId}.");
            }

            Console.WriteLine($"> CONNECT: {link.Source.Id} => {link.TargetId}"); // %%% LOGGER

            workflowBuilder.AddEdge(link.Source.Step, targetNode.Step, link.Condition);
        }
    }

    private ProcessWorkflowNode DefineNode(ExecutorIsh step, ProcessWorkflowNode? parentNode = null, Type? actionType = null)
    {
        ProcessWorkflowNode stepNode = new(step, parentNode, actionType);
        this.Steps[stepNode.Id] = stepNode;

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
            if (!this.Steps.TryGetValue(itemId, out ProcessWorkflowNode? itemNode))
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

    private sealed class ProcessWorkflowNode(ExecutorIsh step, ProcessWorkflowNode? parent = null, Type? actionType = null)
    {
        public string Id => step.Id;

        public ExecutorIsh Step => step;

        public ProcessWorkflowNode? Parent { get; } = parent;

        public List<ProcessWorkflowNode> Children { get; } = [];

        public int Depth => this.Parent?.Depth + 1 ?? 0;

        public Type? ActionType => actionType;
    }

    private sealed record class ProcessWorkflowLink(ProcessWorkflowNode Source, string TargetId, Func<object?, bool>? Condition = null);
}
