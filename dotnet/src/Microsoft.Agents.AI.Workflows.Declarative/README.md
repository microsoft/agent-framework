# Declarative Workflows

Declarative Workflows is a no-code platform for orchestrating AI agents to accomplish complex, multi-step tasks with ease.
It allows users to design, execute, and monitor workflows using simple declarative configurations—no coding required.
By connecting multiple AI agents and services, it enables automation of sophisticated processes that traditionally require custom engineering.

We've provided a set of [Sample Workflows](../../../workflow-samples/) within the `agent-framework` repository.

Please refer to the [README](../../../workflow-samples/README.md) for setup instructions to run the sample workflows in your environment.

As part of our [Getting Started with Declarative Workflows](../../samples/GettingStarted/Workflows/Declarative/README.md),
we've provided a console application that is able to execute any declarative workflow.

Please refer to the [README](../../samples/GettingStarted/Workflows/Declarative/README.md) for configuration instructions.

## Actions

### ⚙️ Foundry Actions

|Action|Description|
|-|-|
|**AddConversationMessage**|Adds a message to the current conversation thread. Useful for dynamically appending information or system responses.
|**CopyConversationMessages**|Duplicates messages from one conversation or context to another. Helps maintain continuity across related interactions.
|**CreateConversation**|Starts a new conversation instance. Used when initiating separate dialogues or workflows.
|**DeleteConversation**|Permanently removes an existing conversation. Helps manage storage and ensure privacy compliance.
|**InvokeAzureAgent**|Triggers an Azure-based AI agent to perform a task or return a response. Useful for leveraging external cognitive services.
|**RetrieveConversationMessage**|Fetches a single message from a conversation history. Enables referencing or reusing specific past exchanges.
|**RetrieveConversationMessages**|Retrieves multiple messages from the conversation history. Useful for context reconstruction or auditing.

### 🧑‍💼 Human Input

|Action|Description|
|-|-|
|**Question**|Presents a query or prompt requiring human input. Integrates human decision-making into automated processes.

### 🧩 State Management

|Action|Description|
|-|-|
|**ClearAllVariables**|Resets all variables in the current context. Ensures a clean state before starting new logic or sessions.
|**EditTableV2**|Modifies data in a structured table format. Useful for updating variable sets or configuration data dynamically.
|**ParseValue**|Extracts or converts data into a usable format. Often used for transforming input before assignment or evaluation.
|**ResetVariable**|Restores a specific variable to its default or initial value. Helps maintain predictable state transitions.
|**SendActivity**|Sends an activity or message to another system or user. Facilitates communication between components or external services.
|**SetMultipleVariables**|Assigns values to multiple variables simultaneously. Useful for batch initialization or updates.
|**SetTextVariable**|Assigns text-based data to a variable. Commonly used for string operations or message composition.
|**SetVariable**|Sets or updates the value of a single variable. Fundamental for maintaining and controlling state within workflows.

### 🧭 Control Flow

|Action|Description|
|-|-|
|**BreakLoop**|Exits the current loop prematurely when a specified condition is met. Useful for preventing unnecessary iterations once a goal is achieved.
|**ConditionGroup**|Defines a set of conditional statements that can be evaluated together. It allows complex decision logic to be grouped for readability and maintainability.
|**ConditionItem**|Represents a single conditional statement within a group. It evaluates a specific logical condition and determines the next step in the flow.
|**ContinueLoop**|Skips the remaining steps in the current iteration and continues with the next loop cycle. Commonly used to bypass specific cases without exiting the loop entirely.
|**EndConversation**|Terminates the current conversation session. It ensures any necessary cleanup or final actions are performed before closing.
|**EndWorkflow**|Ends the current workflow or sub-workflow within a broader conversation flow. This helps modularize complex interactions.
|**Foreach**|Iterates through a collection of items, executing a set of actions for each. Ideal for processing lists or batch operations.
|**GotoAction**|Jumps directly to a specified action within the workflow. Enables non-linear navigation in the logic flow.


