// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Kit;

public sealed class RootExecutorTests
{
    [Fact]
    public async Task InitializeEnvironmentAsync_OnlyQueuesAllowedVariablesAsync()
    {
        // Arrange
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ALLOWED"] = "allowed-value",
                ["HIDDEN"] = "hidden-value",
            })
            .Build();
        DeclarativeWorkflowOptions options =
            new(new MockAgentProvider().Object)
            {
                Configuration = configuration,
                AllowedEnvironmentVariables = ["ALLOWED"],
            };
        TestRootExecutor executor = new(options);
        Mock<IWorkflowContext> sourceContext = new(MockBehavior.Strict);
        sourceContext.Setup(c => c.QueueStateUpdateAsync("ALLOWED", It.IsAny<object?>(), VariableScopeNames.Environment, It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));

        DeclarativeWorkflowContext context = new(sourceContext.Object, executor.Session.State);

        // Act
        await executor.InitializeAsync(context, "ALLOWED", "HIDDEN");

        // Assert
        sourceContext.Verify(c => c.QueueStateUpdateAsync("ALLOWED", It.IsAny<object?>(), VariableScopeNames.Environment, It.IsAny<CancellationToken>()), Times.Once);
        sourceContext.Verify(c => c.QueueStateUpdateAsync("HIDDEN", It.IsAny<object?>(), VariableScopeNames.Environment, It.IsAny<CancellationToken>()), Times.Never);
    }

    private sealed class TestRootExecutor(DeclarativeWorkflowOptions options) : RootExecutor<string>("test_root", options, inputTransform: null)
    {
        public ValueTask InitializeAsync(IWorkflowContext context, params string[] variableNames) =>
            this.InitializeEnvironmentAsync(context, variableNames);

        protected override ValueTask ExecuteAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
            default;
    }
}
