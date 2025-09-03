# Declarative Workflow Ejection (to Code)


### TODO

Visibility into status of Object Model updates/integration:

- [Task #485](https://github.com/microsoft/agent-framework/issues/485): Add Foundry actions to Object Model: 
  https://msazure.visualstudio.com/CCI/_git/ObjectModel/pullrequest/13137388
  (Being reviewed in 9/4 office hours)

- [Task #486](https://github.com/microsoft/agent-framework/issues/486): Introduce `Workflow` root dialog to Object Model: 

- [Task #488](https://github.com/microsoft/agent-framework/issues/488): Introduce `Workflow` variable scope to Object Model (with runtime support): 

> Each of these tasks will require a new Object Model package release before they can be integrated here and affects the YAML definition.


## Thoughts

### Critical

1. Able to generate both C# & Python (then maybe TypeScript, Java, etc...) from .NET interpreter
1. The _Power FX_ expression language is essential to the workflow definition
1. _Power FX_ expressions rely upon "System" and "Env" scoped variables
1. Workflow defined variables ("Topic" or "Global") require default initialization (semantic model)

### Modes

- Equivalent execution when initially translated from YAML to code.
- Developer can introduce changes to the generated code:
    1. Add new executors (custom or action-based)
    1. Modify executors
    1. Remove executors

### Pattern Convergence

Patterns from _Declarative Workflows_ to be promoted as a core _Workflows_ concept:

**Critical**
- System variable management: `LastMessage` `Conversation`, etc...
- PowerFx expression support
- "Foreach" executor for _Workflows_ (Python & .NET) - Includes "Break" and "Continue" semantics

**Sensible**
- Scope definitions (`Topic`/`Workflow`, `Global`, `System`, `Env`)
- Agent provider pattern
- Workflow options

### Open Issues

- Executor protocol alignment (DeclarativeExecutorResult vs ...)
- AIAgentHostExecutor vs InvokeAzureAgent


## Reference

This code snippet shows how to build a workflow from a YAML file and execute it using the Foundry agent provider.

```csharp
DeclarativeWorkflowOptions options = new(new FoundryAgentProvider("https://...", new AzureCliCredential()))
Workflow<string> workflow = DeclarativeWorkflowBuilder.Build<string>("myworkflow.yaml", options);
```

Defining "ejected" workflow should following the same pattern:

```csharp
DeclarativeWorkflowOptions options = new(new FoundryAgentProvider("https://...", new AzureCliCredential()))
Workflow<string> workflow = ...;
```


## Translation

#### Source:

Here is the YAML source for a simple workflow that assings a variable based on input and invokes an Azure agent.

> Now:
```yml
kind: AdaptiveDialog
beginDialog:
  kind: OnActivity
  id: workflow_demo
  actions:
    - kind: SetVariable
      id: set_input_task
      variable: Topic.InputTask
      value: =System.LastMessage

    - kind: AnswerQuestionWithAI
      id: agent_invoke_old
      userInput: =Topic.InputTask.Text
      additionalInstructions: {Env.FOUNDRY_AGENT_ID}
```

> Final:
```yml
kind: Workflow
actions:
  - kind: SetVariable
    id: set_input_task
    variable: Topic.InputTask
    value: =System.LastMessage

  - kind: InvokeAzureAgent
    id: agent_invoke
    input:
    messages: =[Topic.InputTask]
```


#### Option 1: Dedicated executors

This solution uses dedicated executors for each action type, but unrolls the declarative model into executor inputs.

```csharp
// Create workflow options and builder
DeclarativeWorkflowOptions options = new(new FoundryAgentProvider("https://...", new AzureCliCredential()))
DeclarativeWorkflowBuilder builder = new(options);

// Add `SetVariable` executor
SetVariableExecutor setInputTask = new("set_input_task, "Topic.InputTask"", "=System.LastMessage");
builder.AddEdge(builder.Root, setInputTask);

// Add `InvokeAzureAgent` executor
InvokeAgentExecutor agentResponse = 
    new("agent_invoke", "=Env.FOUNDRY_AGENT_ID")
    {
        Input = "=Topic.InputTask"
    };
builder.AddEdge(setInputTask, agentResponse);

// Build the workflow
Workflow<string> workflow = builder.Build<string>();
```


#### Option 2: Create model

Creates the declarative model and interprets it, just like YAML.

```csharp
// Create the root workflow model
Workflow.Builder workflowBuilder = new();
  
// Add `SetVariable` action
workflowBuilder.Actions.Add(
    new SetVariable.Builder()
    {
        Id = new("set_input_task"),
        Variable = InitializablePropertyPath.Create("Topic.InputTask"),
        Value = ValueExpression.Variable("System.LastMessage"),
    });

// Add `InvokeAzureAgent` action
workflowBuilder.Actions.Add(
    new InvokeAzureAgent.Builder()
    {
        Id = new("agent_invoke"),
        Input = ValueExpression.Variable("Topic.InputTask"),
    });

// Build the workflow with options
DeclarativeWorkflowOptions options = new(new FoundryAgentProvider("https://...", new AzureCliCredential()))
Workflow<string> workflow = DeclarativeWorkflowBuilder.Build<string>(workflowBuilder, options);
```


#### Option 3: Explicit executors

This solution uses bespoke executors for each action.

```csharp
internal sealed class SetInputTaskExecutor() : ActionExecutor(id: "set_input_task")
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        await context.QueueStateUpdateAsync("InputTask", ValueExpression.Expression("=System.LastMessage"), "Topic").ConfigureAwait(false);
    }
}

internal sealed class AgentResponseExecutor : AgentActionExecutor(id: "agent_invoke")
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        await .InvokeAgentAsync(
            context,
            agentId: StringExpression.Expression("=Env.FOUNDRY_AGENT_ID"), 
            input: ValueExpression.Expression("=Topic.InputTask"), 
            cancellationToken).ConfigureAwait(false);        
    }
}

// Create workflow options and builder
DeclarativeWorkflowOptions options = new(new FoundryAgentProvider("https://...", new AzureCliCredential()))
DeclarativeWorkflowBuilder builder = new(options);

// Add `SetVariable` executor
SetInputTaskExecutor setInputTask = new();
builder.AddEdge(builder.Root, setInputTask);

// Add `InvokeAzureAgent` executor
AgentResponseExecutor agentResponse = new();
builder.AddEdge(setInputTask, agentResponse);

// Build the workflow
Workflow<string> workflow = builder.Build<string>();
```
