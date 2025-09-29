// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class ProviderTemplate
{
    public ProviderTemplate(
        string workflowId,
        IEnumerable<string> executors,
        IEnumerable<string> instances,
        IEnumerable<string> edges)
    {
        this.Executors = executors;
        this.Instances = instances;
        this.Edges = edges;
        this.RootInstance = workflowId.FormatName();
        this.RootExecutorType = workflowId.FormatType();
    }

    public string? Namespace { get; init; }
    public string? Prefix { get; init; }

    public string RootInstance { get; }
    public string RootExecutorType { get; }

    public IEnumerable<string> Executors { get; }
    public IEnumerable<string> Instances { get; }
    public IEnumerable<string> Edges { get; }

    public static IEnumerable<string> ByLine(IEnumerable<string> templates, bool formatGroup = false)
    {
        foreach (string template in templates)
        {
            foreach (string line in template.ByLine())
            {
                yield return line;
            }

            if (formatGroup)
            {
                yield return string.Empty;
            }
        }
    }
}
