// Copyright (c) Microsoft. All rights reserved.

using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.Entities;

internal sealed record class EntityExtractionResult
{
    public EntityExtractionResult(FormulaValue? value)
    {
        this.Value = value;
        this.ErrorMessage = null;
    }

    public EntityExtractionResult(string errorMessage)
    {
        this.Value = null;
        this.ErrorMessage = errorMessage;
    }

    public FormulaValue? Value { get; }
    public string? ErrorMessage { get; }
    public bool IsValid => this.Value is not null;
}
