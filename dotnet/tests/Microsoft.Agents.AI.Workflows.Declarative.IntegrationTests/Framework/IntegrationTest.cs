// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Reflection;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.Configuration;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;

/// <summary>
/// Base class for workflow tests.
/// </summary>
public abstract class IntegrationTest : IDisposable
{
    public TestOutputAdapter Output { get; }

    protected IntegrationTest(ITestOutputHelper output)
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

    internal static string FormatVariablePath(string variableName, string? scope = null) => $"{scope ?? WorkflowFormulaState.DefaultScopeName}.{variableName}";

    protected static IConfigurationRoot InitializeConfig() =>
        new ConfigurationBuilder()
            .AddJsonFile("appsettings.Development.json", true)
            .AddEnvironmentVariables()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .Build();
}
