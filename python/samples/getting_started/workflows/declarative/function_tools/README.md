# Function Tools Workflow

This sample demonstrates an agent with function tools responding to user queries about a restaurant menu.

## Overview

The workflow showcases:
- **Function Tools**: Agent equipped with tools to query menu data
- **Real Azure OpenAI Agent**: Uses `AzureOpenAIChatClient` to create an agent with tools
- **Agent Registration**: Shows how to register agents with the `WorkflowFactory`

## Tools

The MenuAgent has access to these function tools:

| Tool | Description |
|------|-------------|
| `get_menu()` | Returns all menu items with category, name, and price |
| `get_specials()` | Returns today's special items |
| `get_item_price(name)` | Returns the price of a specific item |

## Menu Data

```
Soups:
  - Clam Chowder - $4.95 (Special)
  - Tomato Soup - $4.95

Salads:
  - Cobb Salad - $9.99
  - House Salad - $4.95

Drinks:
  - Chai Tea - $2.95 (Special)
  - Soda - $1.95
```

## Prerequisites

- Azure OpenAI configured with required environment variables
- Authentication via azure-identity (run `az login` before executing)

## Usage

```bash
python main.py
```

## Example Output

```
Loaded workflow: function-tools-workflow
============================================================
Restaurant Menu Assistant
============================================================

[Bot]: Welcome to the Restaurant Menu Assistant!

[Bot]: Today's soup special is the Clam Chowder for $4.95!

============================================================
Session Complete
============================================================
```

## How It Works

1. Create an Azure OpenAI chat client
2. Create an agent with instructions and function tools
3. Register the agent with the workflow factory
4. Load the workflow YAML and run it with `run_stream()`

```python
# Create the agent with tools
chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())
menu_agent = chat_client.as_agent(
    name="MenuAgent",
    instructions="You are a helpful restaurant menu assistant...",
    tools=[get_menu, get_specials, get_item_price],
)

# Register with the workflow factory
factory = WorkflowFactory(execution_mode="graph")
factory.register_agent("MenuAgent", menu_agent)

# Load and run the workflow
workflow = factory.create_workflow_from_yaml_path(workflow_path)
async for event in workflow.run_stream(inputs={"userInput": "What is the soup of the day?"}):
    ...
```
