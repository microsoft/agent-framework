# Microsoft.Agents.AI.Hosting.AzureFunctions

This package adds Azure Functions integration and serverless hosting for Microsoft Agent Framework on Azure Functions. It builds upon the `Microsoft.Agents.AI.DurableTask` package to provide the following capabilities:

- Stateful, durable execution of agents in distributed, serverless environments
- Automatic conversation history management in supported [Durable Functions backends](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-storage-providers)
- Long-running agent workflows as "durable orchestrator" functions
- Tools and [dashboards](https://learn.microsoft.com/azure/azure-functions/durable/durable-task-scheduler/durable-task-scheduler-dashboard) for managing and monitoring agents and agent workflows

## Install the package

From the command-line:

```bash
dotnet add package Microsoft.Agents.AI.Hosting.AzureFunctions
```

Or directly in your project file:

```xml
<ItemGroup>
  <PackageReference Include="Microsoft.Agents.AI.Hosting.AzureFunctions" Version="[CURRENTVERSION]" />
</ItemGroup>
```

## Usage Examples

For a comprehensive tour of all the functionality, concepts, and APIs, check out the [Azure Functions samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/) in the [Microsoft Agent Framework GitHub repository](https://github.com/microsoft/agent-framework).

### Hosting single agents

This package provides a `ConfigureDurableAgents` extension method on the `FunctionsApplicationBuilder` class to configure the application to host Microsoft Agent Framework agents. These hosted agents are automatically registered as durable entities with the Durable Task runtime and can be invoked via HTTP or Durable Task orchestrator functions.

```csharp
// Create agents using the standard Microsoft Agent Framework.
// Invocable via HTTP via http://localhost:7071/api/agents/SpamDetectionAgent/run
AIAgent spamDetector = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent(
        instructions: "You are a spam detection assistant that identifies spam emails.",
        name: "SpamDetectionAgent");

AIAgent emailAssistant = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent(
        instructions: "You are an email assistant that helps users draft responses to emails with professionalism.",
        name: "EmailAssistantAgent");

// Configure the Functions application to host the agents.
using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableAgents(options =>
    {
        options.AddAIAgent(spamDetector);
        options.AddAIAgent(emailAssistant);
    })
    .Build();
app.Run();
```

By default, each agent can be invoked via a built-in HTTP trigger function at the route `http[s]://[host]/api/agents/{agentName}/run`.

### Orchestrating hosted agents

This package also provides a set of extension methods such as `GetAgent` on the [`TaskOrchestrationContext`](https://learn.microsoft.com/dotnet/api/microsoft.durabletask.taskorchestrationcontext) class for interacting with hosted agents within orchestrations.

```csharp
[Function(nameof(SpamDetectionOrchestration))]
public static async Task<string> SpamDetectionOrchestration(
    [OrchestrationTrigger] TaskOrchestrationContext context)
{
    Email email = context.GetInput<Email>() ?? throw new InvalidOperationException("Email is required");

    // Get the spam detection agent
    DurableAIAgent spamDetectionAgent = context.GetAgent("SpamDetectionAgent");
    AgentThread spamThread = spamDetectionAgent.GetNewThread();

    // Step 1: Check if the email is spam
    AgentRunResponse<DetectionResult> spamDetectionResponse = await spamDetectionAgent.RunAsync<DetectionResult>(
        message:
            $"""
            Analyze this email for spam content and return a JSON response with 'is_spam' (boolean) and 'reason' (string) fields:
            Email ID: {email.EmailId}
            Content: {email.EmailContent}
            """,
        thread: spamThread);
    DetectionResult result = spamDetectionResponse.Result;

    // Step 2: Conditional logic based on spam detection result
    if (result.IsSpam)
    {
        // Handle spam email
        return await context.CallActivityAsync<string>(nameof(HandleSpamEmail), result.Reason);
    }
    else
    {
        // Generate and send response for legitimate email
        DurableAIAgent emailAssistantAgent = context.GetAgent("EmailAssistantAgent");
        AgentThread emailThread = emailAssistantAgent.GetNewThread();

        AgentRunResponse<EmailResponse> emailAssistantResponse = await emailAssistantAgent.RunAsync<EmailResponse>(
            message:
                $"""
                Draft a professional response to this email. Return a JSON response with a 'response' field containing the reply:
                
                Email ID: {email.EmailId}
                Content: {email.EmailContent}
                """,
            thread: emailThread);

        EmailResponse emailResponse = emailAssistantResponse.Result;
        return await context.CallActivityAsync<string>(nameof(SendEmail), emailResponse.Response);
    }
}
```

### Scheduling orchestrations from custom code tools

Agents can also schedule and interact with orchestrations from custom code tools. This is useful for long-running tool use cases where orchestrations need to be executed in the context of the agent.

The `DurableAgentContext.Current` *AsyncLocal* property provides access to the current agent context, which can be used to schedule and interact with orchestrations.

```csharp
class Tools
{
    [Description("Starts a content generation workflow and returns the instance ID for tracking.")]
    public string StartContentGenerationWorkflow(
        [Description("The topic for content generation")] string topic)
    {
        // ContentGenerationWorkflow is an orchestrator function defined in the same project.
        string instanceId = DurableAgentContext.Current.ScheduleNewOrchestration(
            name: nameof(ContentGenerationWorkflow),
            input: topic);

        // Return the instance ID so that it gets added to the LLM context.
        return instanceId;
    }

    [Description("Gets the status of a content generation workflow.")]
    public async Task<OrchestrationMetadata> GetContentGenerationStatus(
        [Description("The instance ID of the workflow to check")] string instanceId,
        [Description("Whether to include detailed information")] bool includeDetails = true)
    {
        OrchestrationMetadata? status = await DurableAgentContext.Current.Client.GetOrchestrationStatusAsync(
            instanceId,
            includeDetails);
        return status ?? throw new InvalidOperationException($"Workflow instance '{instanceId}' not found.");
    }
}
```

These tools are registered with the agent using the `tools` parameter when creating the agent.

```csharp
Tools tools = new();
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent(
        instructions: "You are a content generation assistant that helps users generate content.",
        name: "ContentGenerationAgent",
        tools: [
            AIFunctionFactory.Create(tools.StartContentGenerationWorkflow),
            AIFunctionFactory.Create(tools.GetContentGenerationStatus)
        ]);

using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableAgents(options => options.AddAIAgent(agent))
    .Build();
app.Run();
```

## Feedback & Contributing

We welcome feedback and contributions in [our GitHub repo](https://github.com/microsoft/agent-framework).
