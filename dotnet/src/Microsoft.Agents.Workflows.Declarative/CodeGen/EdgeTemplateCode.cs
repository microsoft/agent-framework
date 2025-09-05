// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class EdgeTemplate
{
    internal EdgeTemplate(string targetId, string? sourceId = null)
    {
        this.SourceId = sourceId.FormatOptional();
        this.TargetId = targetId.FormatName();
    }

    public string? SourceId { get; }
    public string TargetId { get; }
}
