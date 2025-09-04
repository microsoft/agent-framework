// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.Workflows.Declarative.Templates;

internal partial class WorkflowTemplate
{
    internal WorkflowTemplate(
        string workflowId,
        IEnumerable<string> executors,
        IEnumerable<string> instances,
        IEnumerable<string> edges)
    {
        this.Id = workflowId;
        this.Executors = executors;
        this.Instances = instances;
        this.Edges = edges;
    }

    public string Id { get; }
    public string? Namespace { get; init; }
    public IEnumerable<string> Executors { get; }
    public IEnumerable<string> Instances { get; }
    public IEnumerable<string> Edges { get; }

    public static IEnumerable<string> ByLine(IEnumerable<string> templates)
    {
        foreach (string template in templates)
        {
            foreach (string line in template.ByLine())
            {
                yield return line;
            }
        }
    }
}
