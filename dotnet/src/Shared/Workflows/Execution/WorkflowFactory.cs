// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Declarative;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Shared.Workflows;

internal sealed class WorkflowFactory(string workflowFile, WorkflowAgentProvider agentProvider)
{
    public IConfiguration? Configuration { get; init; }

    // Assign to continue an existing conversation
    public string? ConversationId { get; init; }

    // Assign to enable logging
    public ILoggerFactory LoggerFactory { get; init; } = NullLoggerFactory.Instance;

    /// <summary>
    /// Create the workflow from the declarative YAML.  Includes definition of the
    /// <see cref="DeclarativeWorkflowOptions" /> and the associated <see cref="WorkflowAgentProvider"/>.
    /// </summary>
    public Workflow CreateWorkflow()
    {
        // Define the workflow options.
        DeclarativeWorkflowOptions options =
            new(agentProvider)
            {
                Configuration = this.Configuration,
                ConversationId = this.ConversationId,
                LoggerFactory = this.LoggerFactory,
            };

        string workflowPath = Path.Combine(AppContext.BaseDirectory, workflowFile);

        // Use DeclarativeWorkflowBuilder to build a workflow based on a YAML file.
        return DeclarativeWorkflowBuilder.Build<string>(workflowPath, options);
    }
}
