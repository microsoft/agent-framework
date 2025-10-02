// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class EdgeTemplate
{
    public EdgeTemplate(string sourceId, string targetId, string? condition = null)
    {
        this.SourceId = sourceId.FormatName();
        this.TargetId = targetId.FormatName();
        this.Condition = condition;
    }

    public string SourceId { get; }
    public string TargetId { get; }
    public string? Condition { get; }
}
