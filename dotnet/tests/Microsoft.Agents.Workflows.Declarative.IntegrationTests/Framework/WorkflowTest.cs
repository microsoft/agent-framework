// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Reflection;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Extensions.Configuration;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.IntegrationTests.Framework;

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

    internal static string FormatVariablePath(string variableName, string? scope = null) => $"{scope ?? WorkflowFormulaState.DefaultScopeName}.{variableName}";

    protected static IConfigurationRoot InitializeConfig() =>
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .AddEnvironmentVariables()
            .Build();
}
