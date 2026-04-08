// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.FoundryLocal.UnitTests;

public class FoundryLocalClientOptionsTests
{
    [Fact]
    public void ResolveModel_WithExplicitModel_ReturnsModel()
    {
        var options = new FoundryLocalClientOptions { Model = "phi-4-mini" };

        var result = options.ResolveModel();

        Assert.Equal("phi-4-mini", result);
    }

    [Fact]
    public void ResolveModel_WithEnvironmentVariable_ReturnsEnvValue()
    {
        var previousValue = Environment.GetEnvironmentVariable("FOUNDRY_LOCAL_MODEL");
        try
        {
            Environment.SetEnvironmentVariable("FOUNDRY_LOCAL_MODEL", "env-model");
            var options = new FoundryLocalClientOptions();

            var result = options.ResolveModel();

            Assert.Equal("env-model", result);
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_LOCAL_MODEL", previousValue);
        }
    }

    [Fact]
    public void ResolveModel_ExplicitModelOverridesEnvVar()
    {
        var previousValue = Environment.GetEnvironmentVariable("FOUNDRY_LOCAL_MODEL");
        try
        {
            Environment.SetEnvironmentVariable("FOUNDRY_LOCAL_MODEL", "env-model");
            var options = new FoundryLocalClientOptions { Model = "explicit-model" };

            var result = options.ResolveModel();

            Assert.Equal("explicit-model", result);
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_LOCAL_MODEL", previousValue);
        }
    }

    [Fact]
    public void ResolveModel_WithNoModelAndNoEnvVar_Throws()
    {
        var previousValue = Environment.GetEnvironmentVariable("FOUNDRY_LOCAL_MODEL");
        try
        {
            Environment.SetEnvironmentVariable("FOUNDRY_LOCAL_MODEL", null);
            var options = new FoundryLocalClientOptions();

            var ex = Assert.Throws<InvalidOperationException>(() => options.ResolveModel());

            Assert.Contains("FOUNDRY_LOCAL_MODEL", ex.Message);
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_LOCAL_MODEL", previousValue);
        }
    }

    [Fact]
    public void ResolveModel_WithWhitespaceModel_Throws()
    {
        var previousValue = Environment.GetEnvironmentVariable("FOUNDRY_LOCAL_MODEL");
        try
        {
            Environment.SetEnvironmentVariable("FOUNDRY_LOCAL_MODEL", null);
            var options = new FoundryLocalClientOptions { Model = "   " };

            Assert.Throws<InvalidOperationException>(() => options.ResolveModel());
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_LOCAL_MODEL", previousValue);
        }
    }

    [Fact]
    public void DefaultValues_AreCorrect()
    {
        var options = new FoundryLocalClientOptions();

        Assert.Null(options.Model);
        Assert.Equal("AgentFramework", options.AppName);
        Assert.True(options.Bootstrap);
        Assert.True(options.PrepareModel);
        Assert.True(options.StartWebService);
        Assert.Null(options.WebServiceUrl);
    }

    [Fact]
    public void Properties_CanBeSet()
    {
        var webUrl = new Uri("http://localhost:9999");
        var options = new FoundryLocalClientOptions
        {
            Model = "test-model",
            AppName = "TestApp",
            Bootstrap = false,
            PrepareModel = false,
            StartWebService = false,
            WebServiceUrl = webUrl,
        };

        Assert.Equal("test-model", options.Model);
        Assert.Equal("TestApp", options.AppName);
        Assert.False(options.Bootstrap);
        Assert.False(options.PrepareModel);
        Assert.False(options.StartWebService);
        Assert.Equal(webUrl, options.WebServiceUrl);
    }
}
