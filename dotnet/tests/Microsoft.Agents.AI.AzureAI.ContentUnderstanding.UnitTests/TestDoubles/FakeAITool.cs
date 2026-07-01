// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Minimal <see cref="AITool"/> stand-in for Phase 9 tests. Carries a name so assertions can
/// verify the caller's <c>file_search</c> tool is forwarded into <c>AIContext.Tools</c>.
/// </summary>
internal sealed class FakeAITool : AITool
{
    public FakeAITool(string name = "file_search")
    {
        this._name = name;
    }

    private readonly string _name;

    public override string Name => this._name;
}
