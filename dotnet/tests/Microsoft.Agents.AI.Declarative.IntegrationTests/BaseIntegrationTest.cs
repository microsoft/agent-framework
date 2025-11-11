// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Reflection;
using Microsoft.Extensions.Configuration;
using Shared.IntegrationTests;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Declarative.IntegrationTests;

/// <summary>
/// Base class for integration tests.
/// </summary>
public abstract class BaseIntegrationTest : IDisposable
{
    private IConfigurationRoot? _configuration;
    private AzureAIConfiguration? _foundryConfiguration;
    private OpenAIConfiguration? _openAIConfiguration;
    private FoundryProjectConfiguration? _foundryProjectConfiguration;

    protected IConfigurationRoot Configuration => this._configuration ??= InitializeConfig();

    internal AzureAIConfiguration FoundryConfiguration
    {
        get
        {
            this._foundryConfiguration ??= this.Configuration.GetSection("AzureAI").Get<AzureAIConfiguration>();
            Assert.NotNull(this._foundryConfiguration);
            return this._foundryConfiguration;
        }
    }

    internal OpenAIConfiguration OpenAIConfiguration
    {
        get
        {
            this._openAIConfiguration ??= this.Configuration.GetSection("OpenAI").Get<OpenAIConfiguration>();
            Assert.NotNull(this._openAIConfiguration);
            return this._openAIConfiguration;
        }
    }

    internal FoundryProjectConfiguration FoundryProjectConfiguration
    {
        get
        {
            this._foundryProjectConfiguration ??= this.Configuration.GetSection("FoundryProject").Get<FoundryProjectConfiguration>();
            Assert.NotNull(this._foundryProjectConfiguration);
            return this._foundryProjectConfiguration;
        }
    }

    public TestOutputAdapter Output { get; }

    protected BaseIntegrationTest(ITestOutputHelper output)
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

    private static IConfigurationRoot InitializeConfig() =>
        new ConfigurationBuilder()
            .AddJsonFile("appsettings.Development.json", true)
            .AddEnvironmentVariables()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .Build();
}
