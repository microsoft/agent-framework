---
status: proposed
contact: westey-m
date: 2026-01-27
deciders: sergeymenshykh, markwallace, rbarreto, dmytrostruk, westey-m, eavanvalkenburg, stephentoub, lokitoth, alliscode, taochenosu, moonbox3
consulted: 
informed: 
---

# AgentRunContext for Agent Run

## Context and Problem Statement

During an agent run, various components involved in the execution (middleware, filters, tools, nested agents, etc.) may need access to contextual information about the current run, such as:

1. The agent that is executing the run
2. The session associated with the run
3. The request messages passed to the agent
4. The run options controlling the agent's behavior

Additionally, some components may need to modify this context during execution, for example:

- Replacing the session with a different one
- Modifying the request messages before they reach the agent core
- Updating or replacing the run options entirely

Currently, there is no standardized way to access or modify this context from arbitrary code that executes during an agent run, especially from deeply nested call stacks where the context is not explicitly passed.

## Sample Scenario

When using an Agent as an AIFunction developers may want to pass context from the parent agent run to the child agent run. For example, the developer may want to copy chat history to the child agent, or share the same session across both agents.

To enable these scenarios, we need a way to access the parent agent run context, including e.g. the parent agent itself, the parent agent session, and the parent run options from function tool calls.

```csharp
    public static AIFunction AsAIFunctionWithSessionPropagation(this ChatClientAgent agent, AIFunctionFactoryOptions? options = null)
    {
        Throw.IfNull(agent);

        [Description("Invoke an agent to retrieve some information.")]
        async Task<string> InvokeAgentAsync(
            [Description("Input query to invoke the agent.")] string query,
            CancellationToken cancellationToken)
        {
            // Get the session from the parent agent and pass it to the child agent.
            var session = AIAgent.CurrentRunContext?.Session;

            // Alternatively, the developer may want to create a new session but copy over the chat history from the parent agent.
            // var parentChatHistory = AIAgent.CurrentRunContext?.Session?.GetService<IList<ChatMessage>>();
            // if (parentChatHistory != null)
            // {
            //     var chp = new InMemoryChatHistoryProvider();
            //     foreach (var message in parentChatHistory)
            //     {
            //         chp.Add(message);
            //     }
            //     session = agent.GetNewSession(chp);
            // }

            var response = await agent.RunAsync(query, session: session, cancellationToken: cancellationToken).ConfigureAwait(false);
            return response.Text;
        }

        options ??= new();
        options.Name ??= SanitizeAgentName(agent.Name);
        options.Description ??= agent.Description;

        return AIFunctionFactory.Create(InvokeAgentAsync, options);
    }
```

## Decision Drivers

- Components executing during an agent run need access to run context without explicit parameter passing through every layer
- Context should flow naturally across async calls without manual propagation
- The design should allow modification of context properties by agent decorators (e.g., replacing options or session)
- Solution should be consistent with patterns used in similar frameworks (e.g., `FunctionInvokingChatClient.CurrentContext` `HttpContext.Current`, `Activity.Current`)

## Considered Options

- **Option 1**: Pass context explicitly through all method signatures
- **Option 2**: Use `AsyncLocal<T>` to provide ambient context accessible anywhere during the run
- **Option 3**: Use a combination of explicit parameters for `RunCoreAsync` and `AsyncLocal<T>` for ambient access

## Decision Outcome

Chosen option: **Option 3** - Combination of explicit parameters and AsyncLocal ambient access.

This approach provides the best of both worlds:

1. **Explicit parameters are passed to `RunCoreAsync`**: The core agent implementation receives the parameters explicitly, making it clear what data is available and enabling easy unit testing. Any modification of these in a decorator will require calling `RunAsync` on the inner agent with the updated parameters, which would result in the inner agent creating a new `AgentRunContext` instance.

   ```csharp
    public async Task<AgentResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {

        CurrentRunContext = new(this, session, messages as IReadOnlyCollection<ChatMessage> ?? messages.ToList(), options);
        return await this.RunCoreAsync(messages, session, options, cancellationToken).ConfigureAwait(false);
    }
   ```

2. **`AsyncLocal<AgentRunContext?>` for ambient access**: The context is stored in an `AsyncLocal<T>` field, making it accessible from any code executing during the agent run via a static property.

    The main scenario for this is to allow deeply nested components (e.g., tools, chat client middleware) to access the context without needing to pass it through every method signature. These are external components that cannot easily be modified to accept additional parameters. For internal components, we prefer passing any parameters explicitly.

   ```csharp
   public static AgentRunContext? CurrentRunContext
   {
       get => s_currentContext.Value;
       protected set => s_currentContext.Value = value;
   }
   ```

### AgentRunContext Design

The `AgentRunContext` class encapsulates all run-related state:

```csharp
public class AgentRunContext
{
    public AgentRunContext(
        AIAgent agent,
        AgentSession? session,
        IReadOnlyCollection<ChatMessage> requestMessages,
        AgentRunOptions? agentRunOptions)

    public AIAgent Agent { get; }
    public AgentSession? Session { get; }
    public IReadOnlyCollection<ChatMessage> RequestMessages { get; }
    public AgentRunOptions? RunOptions { get; }
}
```

Key design decisions:

- **All properties are read-only**: While some of the sub-properties on the provided properties (like `AgentRunOptions.AllowBackgroundResponses`) may be mutable, the `AgentRunContext` itself is immutable and we want to discourage anyone modifying the values in the context.  Modifying the context is unlikely to result in the desired behavior, as the values will typically already have been used by the time any custom code accesses them.

### Benefits

1. **Ambient Access**: Any code executing during the run can access context via `AIAgent.CurrentRunContext` without needing explicit parameters
2. **Async Flow**: `AsyncLocal<T>` automatically flows across async/await boundaries
3. **Modifiability**: Components can modify or replace session, messages, or options as needed
4. **Testability**: The explicit parameter to `RunCoreAsync` makes unit testing straightforward
