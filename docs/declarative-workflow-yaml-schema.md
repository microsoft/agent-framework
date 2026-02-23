# Declarative Workflow YAML Schema Reference

A _Declarative Workflow_ lets you orchestrate AI agents and define complex, multi-step automation using a single YAML file — no code required.

This document provides a complete reference for the YAML schema used to author declarative workflows in the Microsoft Agent Framework.

## Table of Contents

- [Top-Level Structure](#top-level-structure)
- [Triggers](#triggers)
- [Actions Reference](#actions-reference)
  - [Foundry Actions](#-foundry-actions)
  - [Human Input](#-human-input)
  - [State Management](#-state-management)
  - [Control Flow](#-control-flow)
- [Expressions](#expressions)
- [Variables](#variables)
- [Input Configuration](#input-configuration)
- [Output Configuration](#output-configuration)
- [Complete Examples](#complete-examples)

---

## Top-Level Structure

Every declarative workflow YAML file begins with a top-level `kind` property and a `trigger` block:

```yaml
kind: Workflow
trigger:
  kind: OnConversationStart
  id: my_workflow
  actions:
    - # ... action list
```

| Property  | Type   | Required | Description                                       |
|-----------|--------|----------|---------------------------------------------------|
| `kind`    | string | ✅       | Must be `Workflow`.                                |
| `trigger` | object | ✅       | Defines when and how the workflow begins executing.|

---

## Triggers

Triggers define the entry point for the workflow. Currently, the supported trigger is:

### `OnConversationStart`

Fires when a new conversation begins with the workflow.

```yaml
trigger:
  kind: OnConversationStart
  id: workflow_demo
  actions:
    - # ... first action
```

| Property  | Type   | Required | Description                                    |
|-----------|--------|----------|------------------------------------------------|
| `kind`    | string | ✅       | Must be `OnConversationStart`.                 |
| `id`      | string | ✅       | A unique identifier for the trigger.           |
| `actions` | list   | ✅       | An ordered list of actions to execute.         |

---

## Actions Reference

Actions are the building blocks of a workflow. Each action has a `kind` property that determines its type, and an `id` that uniquely identifies it within the workflow.

### Common Properties

All actions share these common properties:

| Property      | Type   | Required | Description                                                  |
|---------------|--------|----------|--------------------------------------------------------------|
| `kind`        | string | ✅       | The action type (e.g., `SendActivity`, `SetVariable`).       |
| `id`          | string | ✅       | A unique identifier for this action within the workflow.     |
| `displayName` | string | ❌       | A human-readable label for the action (for tooling/logging). |

---

### ⚙️ Foundry Actions

Actions for interacting with AI agents and managing conversations.

#### `InvokeAzureAgent`

Triggers an Azure-based AI agent to perform a task or return a response.

```yaml
- kind: InvokeAzureAgent
  id: invoke_analyst
  conversationId: =System.ConversationId
  agent:
    name: AnalystAgent
  input:
    messages: =UserMessage("Analyze this data")
    arguments:
      IssueDescription: =Local.Description
    externalLoop:
      when: =Not(Local.Parameters.IsResolved)
  output:
    messages: Local.AgentResponse
    responseObject: Local.Parameters
    autoSend: true
```

| Property         | Type   | Required | Description                                                                  |
|------------------|--------|----------|------------------------------------------------------------------------------|
| `agent.name`     | string | ✅       | Name of the Azure agent to invoke. Can be an expression.                     |
| `conversationId` | string | ❌       | Conversation ID for the agent interaction. Defaults to the current conversation. |
| `input`          | object | ❌       | Input configuration. See [Input Configuration](#input-configuration).        |
| `output`         | object | ❌       | Output configuration. See [Output Configuration](#output-configuration).     |

#### `CreateConversation`

Starts a new conversation instance and stores its ID in a variable.

```yaml
- kind: CreateConversation
  id: conversation_support
  conversationId: Local.SupportConversationId
```

| Property         | Type   | Required | Description                                         |
|------------------|--------|----------|-----------------------------------------------------|
| `conversationId` | string | ✅       | Variable to store the new conversation ID.          |

#### `DeleteConversation`

Permanently removes an existing conversation.

#### `AddConversationMessage`

Adds a message to a conversation thread.

#### `CopyConversationMessages`

Duplicates messages from one conversation context to another.

#### `RetrieveConversationMessage`

Fetches a single message from a conversation history.

#### `RetrieveConversationMessages`

Retrieves multiple messages from the conversation history.

---

### 🧑‍💼 Human Input

#### `Question`

Presents a query or prompt requiring human input, integrating human decision-making into automated processes.

---

### 🧩 State Management

Actions for managing workflow variables and state.

#### `SetVariable`

Sets or updates the value of a single variable. Supports expressions.

```yaml
- kind: SetVariable
  id: set_count
  variable: Local.TurnCount
  value: =Local.TurnCount + 1
```

| Property   | Type   | Required | Description                                         |
|------------|--------|----------|-----------------------------------------------------|
| `variable` | string | ✅       | The variable to set (e.g., `Local.MyVar`).          |
| `value`    | any    | ✅       | The value or expression to assign.                  |

#### `SetTextVariable`

Assigns text-based data to a variable with support for inline string interpolation.

```yaml
- kind: SetTextVariable
  id: set_instructions
  variable: Local.TaskInstructions
  value: |-
    # TASK
    Address the following user request:

    {Local.InputTask}

    # FACTS
    {MessageText(Local.TaskFacts)}
```

| Property   | Type   | Required | Description                                                       |
|------------|--------|----------|-------------------------------------------------------------------|
| `variable` | string | ✅       | The variable to set.                                              |
| `value`    | string | ✅       | Text value with `{expression}` interpolation support.             |

#### `SetMultipleVariables`

Assigns values to multiple variables simultaneously.

#### `ResetVariable`

Restores a specific variable to its default or initial value.

```yaml
- kind: ResetVariable
  id: clear_seed
  variable: Local.SeedTask
```

| Property   | Type   | Required | Description                             |
|------------|--------|----------|-----------------------------------------|
| `variable` | string | ✅       | The variable to reset.                  |

#### `ClearAllVariables`

Resets all variables in the current context.

#### `ParseValue`

Extracts or converts data into a usable format.

#### `EditTableV2`

Modifies data in a structured table format.

#### `SendActivity`

Sends a message or activity to the user or another system.

```yaml
- kind: SendActivity
  id: notify_user
  activity: "Created ticket #{Local.TicketParameters.TicketId}"
```

| Property   | Type   | Required | Description                                                          |
|------------|--------|----------|----------------------------------------------------------------------|
| `activity` | string | ✅       | The message to send. Supports `{expression}` string interpolation.   |

---

### 🧭 Control Flow

Actions for branching, looping, and controlling workflow execution.

#### `ConditionGroup`

Defines a set of conditional branches. Each condition is evaluated in order; the first matching branch executes.

```yaml
- kind: ConditionGroup
  id: check_completion
  conditions:
    - condition: =Local.Parameters.IsResolved
      id: resolved_branch
      actions:
        - kind: SendActivity
          id: notify_resolved
          activity: "Issue resolved!"

    - condition: =Local.TurnCount < 4
      id: retry_branch
      actions:
        - kind: GotoAction
          id: goto_retry
          actionId: invoke_agent

  elseActions:
    - kind: SendActivity
      id: fallback
      activity: "Let's try again later..."
```

| Property      | Type   | Required | Description                                              |
|---------------|--------|----------|----------------------------------------------------------|
| `conditions`  | list   | ✅       | Ordered list of `ConditionItem` objects.                 |
| `elseActions` | list   | ❌       | Actions to execute if no conditions match.               |

Each **ConditionItem** has:

| Property    | Type   | Required | Description                                       |
|-------------|--------|----------|---------------------------------------------------|
| `condition` | string | ✅       | A PowerFx expression that evaluates to a boolean. |
| `id`        | string | ✅       | Unique identifier for this condition.             |
| `actions`   | list   | ✅       | Actions to execute if the condition is true.      |
| `displayName` | string | ❌    | Human-readable label for the condition.           |

#### `Foreach`

Iterates through a collection of items, executing a set of actions for each.

```yaml
- kind: Foreach
  id: iterate_items
  items: =Local.agent_output.items
  value: Local.currentItem
  index: Local.index
  actions:
    - kind: SendActivity
      id: show_item
      activity: "{Local.currentItem}"
```

| Property  | Type   | Required | Description                                       |
|-----------|--------|----------|---------------------------------------------------|
| `items`   | string | ✅       | Expression evaluating to a collection to iterate. |
| `value`   | string | ✅       | Variable to hold the current item.                |
| `index`   | string | ❌       | Variable to hold the current index.               |
| `actions` | list   | ✅       | Actions to execute for each item.                 |

#### `GotoAction`

Jumps directly to a specified action within the workflow, enabling non-linear navigation.

```yaml
- kind: GotoAction
  id: goto_start
  actionId: invoke_agent
```

| Property   | Type   | Required | Description                                |
|------------|--------|----------|--------------------------------------------|
| `actionId` | string | ✅       | The `id` of the target action to jump to.  |

#### `EndWorkflow`

Terminates the current workflow.

```yaml
- kind: EndWorkflow
  id: all_done
```

#### `EndConversation`

Terminates the current conversation session.

```yaml
- kind: EndConversation
  id: end_session
```

#### `BreakLoop`

Exits the current loop prematurely when a specified condition is met.

#### `ContinueLoop`

Skips the remaining steps in the current iteration and continues with the next loop cycle.

---

## Expressions

Declarative workflows use **PowerFx expressions** for dynamic values. Expressions are prefixed with `=` to distinguish them from literal string values.

### Expression Syntax

```yaml
# Literal string value
value: "Hello World"

# Expression (note the = prefix)
value: =Local.TurnCount + 1

# Expression in a condition
condition: =Local.Parameters.IsResolved

# Multi-line expression
condition: |-
  =Not(Local.ServiceParameters.IsResolved)
   And
   Not(Local.ServiceParameters.NeedsTicket)
```

### String Interpolation

Within `activity` and `SetTextVariable` `value` fields, use curly braces `{expression}` for inline interpolation:

```yaml
activity: "Created ticket #{Local.TicketId}"
```

### Common Functions

| Function                | Description                                            |
|-------------------------|--------------------------------------------------------|
| `UserMessage(text)`     | Wraps text as a user message object.                   |
| `MessageText(messages)` | Extracts plain text from a message object.             |
| `IsBlank(value)`        | Returns true if the value is blank or empty.           |
| `Find(needle, haystack)`| Searches for a substring within a string.              |
| `Upper(text)`           | Converts text to uppercase.                            |
| `Not(condition)`        | Logical negation.                                      |
| `CountRows(table)`      | Returns the number of rows in a table/collection.      |
| `First(table)`          | Returns the first item from a table/collection.        |
| `Search(table, ...)`    | Searches a table for matching records.                 |
| `ForAll(table, expr)`   | Applies an expression to every item in a table.        |
| `Concat(table, ...)`    | Concatenates values from a table into a string.        |

---

## Variables

Variables are used to store and pass data throughout the workflow. They are scoped into two namespaces:

### `Local` Variables

Workflow-scoped variables that persist for the duration of the workflow execution. You define them implicitly by assigning to them.

```yaml
# Set a local variable
- kind: SetVariable
  id: set_count
  variable: Local.TurnCount
  value: 0

# Use a local variable in an expression
condition: =Local.TurnCount < 4
```

### `System` Variables

Read-only system-provided context variables.

| Variable                | Description                                       |
|-------------------------|---------------------------------------------------|
| `System.ConversationId` | The ID of the current conversation.               |
| `System.LastMessage`    | The last message received.                        |
| `System.LastMessage.Text` | The text content of the last message.           |

---

## Input Configuration

The `input` block on `InvokeAzureAgent` controls what data the agent receives.

### `messages`

Provide explicit messages to the agent:

```yaml
input:
  messages: =UserMessage("Analyze this data")
```

### `arguments`

Pass named arguments to the agent:

```yaml
input:
  arguments:
    IssueDescription: =Local.Description
    AttemptedSteps: =Local.Steps
```

### `externalLoop`

Causes the agent to be invoked repeatedly until a condition becomes false:

```yaml
input:
  externalLoop:
    when: =Not(Local.Parameters.IsResolved)
```

---

## Output Configuration

The `output` block on `InvokeAzureAgent` controls how the agent's response is captured.

### `messages`

Store the agent's response messages in a variable:

```yaml
output:
  messages: Local.AgentResponse
```

### `responseObject`

Parse the agent's response as a structured object:

```yaml
output:
  responseObject: Local.Parameters
```

### `autoSend`

Automatically forward the agent's response to the user:

```yaml
output:
  autoSend: true
```

---

## Complete Examples

The [`workflow-samples/`](../workflow-samples/) directory contains complete, runnable examples:

| Sample | Description |
|--------|-------------|
| [Marketing.yaml](../workflow-samples/Marketing.yaml) | Sequential agent pipeline — analyst → writer → editor |
| [MathChat.yaml](../workflow-samples/MathChat.yaml) | Conversational loop between a student and teacher agent with turn limits |
| [CustomerSupport.yaml](../workflow-samples/CustomerSupport.yaml) | Multi-agent support workflow with ticket creation, routing, and escalation |
| [DeepResearch.yaml](../workflow-samples/DeepResearch.yaml) | Complex "Magentic" orchestration with dynamic agent selection, progress tracking, and iterative replanning |

### Minimal Example

```yaml
kind: Workflow
trigger:
  kind: OnConversationStart
  id: hello_world
  actions:

    - kind: InvokeAzureAgent
      id: ask_agent
      conversationId: =System.ConversationId
      agent:
        name: MyAgent

    - kind: EndWorkflow
      id: done
```

### Looping Example

```yaml
kind: Workflow
trigger:
  kind: OnConversationStart
  id: retry_loop
  actions:

    - kind: InvokeAzureAgent
      id: ask_agent
      conversationId: =System.ConversationId
      agent:
        name: SolverAgent
      output:
        responseObject: Local.Result

    - kind: SetVariable
      id: increment
      variable: Local.Attempt
      value: =Local.Attempt + 1

    - kind: ConditionGroup
      id: check_done
      conditions:
        - condition: =Local.Result.IsSolved
          id: solved
          actions:
            - kind: SendActivity
              id: success
              activity: "Solved in {Local.Attempt} attempts!"
            - kind: EndWorkflow
              id: done

        - condition: =Local.Attempt < 5
          id: retry
          actions:
            - kind: GotoAction
              id: goto_retry
              actionId: ask_agent

      elseActions:
        - kind: SendActivity
          id: give_up
          activity: "Could not solve after {Local.Attempt} attempts."
        - kind: EndWorkflow
          id: done_failed
```

---

## Further Reading

- [Declarative Workflows Overview](../dotnet/src/Microsoft.Agents.AI.Workflows.Declarative/README.md)
- [Getting Started — Running Declarative Workflows](../dotnet/samples/GettingStarted/Workflows/Declarative/README.md)
- [Workflow Samples](../workflow-samples/README.md)
