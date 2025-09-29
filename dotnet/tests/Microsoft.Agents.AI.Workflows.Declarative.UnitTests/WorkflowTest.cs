// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// Base class for workflow tests.
/// </summary>
public abstract class WorkflowTest : IDisposable
{
    public TestOutputAdapter Output { get; }

    protected WorkflowTest(ITestOutputHelper output)
    {
        this.Output = new TestOutputAdapter(output);
        Console.SetOut(this.Output);
        SetProduct();
    }

    public void Dispose()
    {
        this.Dispose(isDisposing: true);
        GC.SuppressFinalize(this);
    }

    protected virtual void Dispose(bool isDisposing)
    {
        if (isDisposing)
        {
            this.Output.Dispose();
        }
    }

    protected static void SetProduct()
    {
        if (!ProductContext.IsLocalScopeSupported())
        {
            ProductContext.SetContext(Product.Foundry);
        }
    }

    internal static string? FormatOptionalPath(string? variableName, string? scope = null) =>
        variableName is null ? null : FormatVariablePath(variableName, scope);

    internal static string FormatVariablePath(string variableName, string? scope = null) => $"{scope ?? WorkflowFormulaState.DefaultScopeName}.{variableName}";
}
