# Declarative Single Agents

The schema for declarative single agents is documented [here](https://github.com/microsoft/prompty/tree/dev/specification/prompty).
The schema will be supported by multiple teams across Microsoft.
This specification describes how declarative single agents will be supported in the Agent Framework.

## Requirements

- Alignment with the [standard schema for declarative single agents](https://github.com/microsoft/prompty/tree/dev/specification/prompty)
- Support for multiple different agents types and services
    - For example: Chat client agents, Azure AI Foundry agents, A2A agents, ...
- Extensible to support new agent types
- Extensible to support new agent capabilities 
    - For example add new tool types
- Ability to include variables to allow the agent definition to be customised
    - For example, read an endpoint URL from an environment variable or customise the agent instructions
- Ability to define an agent inline in a workflow declarative representation

## Developer Experience

As a developer I can define a single agent declaratively e.g., using a YAML file and then create an instance of that agent so that I can execute an agent run.

A YAML representation of an agent could look like this:

```yaml
kind: GptComponentMetadata
type: chat_client_agent
name: Assistant
description: Helpful assistant
instructions: You are a helpful assistant. You answer questions is the language specified by the user. You return your answers in a JSON format.
model:
  options:
    temperature: 0.9
    top_p: 0.95
    response_format:
      type: json_schema
      json_schema:
      name: assistant_response
      strict: true
      schema:
        $schema: http://json-schema.org/draft-07/schema#
        type: object
        properties:
          language:
            type: string
            description: The language of the answer.
          answer:
            type: string
            description: The answer text.
          required:
            - language
            - answer
          additionalProperties: false
```

- The agent `type` is a chat client agent
- The agent `name`, `description` and `instructions` are provided inline. The instructions will support templating.
- The chat options which will be used are defined using the `model.options

**Note: The `kind` property is a temporary name which is required to allow this definition to be used with `Microsoft.Bost.ObjectModel`**

The code to create an agent using the above YAML would look like this:

```csharp
// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create an AI agent declaratively with Azure OpenAI as the backend.

using System;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.Declarative;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create the chat client
IChatClient chatClient = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
     .GetChatClient(deploymentName)
     .AsIChatClient();

// Alternatively, you can define the response format using as YAML for better readability.
var textYaml =
    """
    ...
    """;
// Create the agent from the YAML definition.
var agentFactory = new ChatClientAgentFactory();
var agent = await agentFactory.CreateFromYamlAsync(textYaml, new() { ChatClient = chatClient });

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync("Tell me a joke about a pirate in English."));
```

1. The `IChatClient` is created and will be passed as an option when creating the agent
1. The `ChatClientAgentFactory` is an implementation of `AgentFactory` which creates a chat client agent
    - The `IChatClient` can be provided directly of resolved from a service provider
1. `CreateFromYamlAsync` is an extension method which parses the YAMl using `Microsoft.Bots.ObjectModel`

## `AgentFactory` Abstractions

`AgentFactory` is the main abstraction which must be extended to provide a factory for creating agents of a specific type.

**Note: The agent definition can include an id in which case the agent will be retrieved and not created.**

```csharp
/// <summary>
/// Represents a factory for creating <see cref="AIAgent"/> instances.
/// </summary>
public abstract class AgentFactory
{
    /// <summary>
    /// Gets the types of agents this factory can create.
    /// </summary>
    public IReadOnlyList<string> Types { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFactory"/> class.
    /// </summary>
    /// <param name="types">Types of agent this factory can create</param>
    protected AgentFactory(IEnumerable<string> types)
    {
        this.Types = [.. types];
    }

    /// <summary>
    /// Return true if this instance of <see cref="AgentFactory"/> supports creating agents from the provided <see cref="GptComponentMetadata"/>
    /// </summary>
    /// <param name="agentDefinition">Definition of the agent to check is supported.</param>
    public bool IsSupported(GptComponentMetadata agentDefinition)
    {
        return this.Types.Any(s => string.Equals(s, agentDefinition.GetTypeValue(), StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>
    /// Create a <see cref="AIAgent"/> from the specified <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="agentDefinition">Definition of the agent to create.</param>
    /// <param name="agentCreationOptions">Options used when creating the agent.</param>
    /// <param name="cancellationToken">Optional cancellation token.</param>
    /// <return>The created <see cref="AIAgent"/>, if null the agent type is not supported.</return>
    public async Task<AIAgent> CreateAsync(GptComponentMetadata agentDefinition, AgentCreationOptions agentCreationOptions, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentDefinition);

        var agent = await this.TryCreateAsync(agentDefinition, agentCreationOptions, cancellationToken).ConfigureAwait(false);
        return agent ?? throw new NotSupportedException($"Agent type {agentDefinition.GetTypeValue()} is not supported.");
    }

    /// <summary>
    /// Tries to create a <see cref="AIAgent"/> from the specified <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="agentDefinition">Definition of the agent to create.</param>
    /// <param name="agentCreationOptions">Options used when creating the agent.</param>
    /// <param name="cancellationToken">Optional cancellation token.</param>
    /// <return>The created <see cref="AIAgent"/>, if null the agent type is not supported.</return>
    public abstract Task<AIAgent?> TryCreateAsync(GptComponentMetadata agentDefinition, AgentCreationOptions agentCreationOptions, CancellationToken cancellationToken = default);
}
```

The `AgentCreationOptions` are provided to the factory when creating an agent instance.

```csharp
/// <summary>
/// Optional parameters for agent creation used when create an <see cref="AIAgent"/>
/// using an instance of <see cref="AgentFactory"/>.
/// <remarks>
/// Implementors of <see cref="AgentFactory"/> can extend this class to provide
/// agent specific creation options.
/// </remarks>
/// </summary>
public class AgentCreationOptions
{
    /// <summary>
    /// Gets or sets the <see cref="IChatClient"/> instance to use when creating the <see cref="AIAgent"/>.
    /// </summary>
    public IChatClient? ChatClient { get; set; } = null;

    /// <summary>
    /// Gets or sets the <see cref="IServiceProvider"/> instance to use when creating the <see cref="AIAgent"/>.
    /// </summary>
    public IServiceProvider? ServiceProvider { get; set; } = null;

    /// <summary>
    /// Gets or sets the <see cref="ILoggerFactory"/> instance to use when creating the <see cref="AIAgent"/>.
    /// </summary>
    public ILoggerFactory? LoggerFactory { get; set; } = null;
}
```