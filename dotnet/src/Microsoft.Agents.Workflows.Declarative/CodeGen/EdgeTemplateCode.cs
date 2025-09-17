// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class EdgeTemplate
{
    public EdgeTemplate(string sourceId, string targetId)
    {
        this.SourceId = sourceId.FormatName();
        this.TargetId = targetId.FormatName();
    }

    public string SourceId { get; }
    public string TargetId { get; }
}
