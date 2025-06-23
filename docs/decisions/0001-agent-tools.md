---
# These are optional elements. Feel free to remove any of them.
status: {proposed}
contact: {dmytrostruk}
date: {2025-06-23}
deciders: {stephentoub, markwallace-microsoft, RogerBarreto, westey-m}
consulted: {}
informed: {}
---

# Agent Tools

## Context and Problem Statement

AI agents increasingly rely on diverse tools like function calling, file search, and computer use, but integrating each tool often requires custom, inconsistent implementations. A unified abstraction for tool usage is essential to simplify development, ensure consistency, and enable scalable, reliable agent performance across varied tasks.

## Decision Drivers

- The abstraction must provide a consistent API for all tools to reduce complexity and improve developer experience.
- The design should allow seamless integration of new tools without significant changes to existing implementations.
- Robust mechanisms for managing tool-specific errors and timeouts are required for reliability.
- The abstraction should support a fallback approach to directly use unsupported or custom tools, bypassing standard abstractions when necessary.

## Considered Options

### Option 1: Use ChatOptions.RawRepresentationFactory for Provider-Specific Tools

#### Description

Utilize the existing `ChatOptions.RawRepresentationFactory` to inject provider-specific tools (e.g., for an AI provider like Foundry) without extending the `AITool` abstract class from `Microsoft.Extensions.AI`.

```csharp
ChatOptions options = new()
{
    RawRepresentationFactory = _ => new ResponseCreationOptions()
    {
        Tools = { ... }, // backend-specific tools
    },
};
```

#### Pros

- No development work needed; leverages existing `Microsoft.Extensions.AI` functionality.
- Flexible for integrating tools from any AI provider without modifying the `AITool`.
- Minimal codebase changes, reducing the risk of introducing errors.

#### Cons

- Requires a separate mechanism to register tools, complicating the developer experience.
- Developers must know the specific AI provider (via `IChatClient`) to configure tools, reducing abstraction.
- Inconsistent with the `AITool` abstraction, leading to fragmented tool usage patterns.
- Poor tool discoverability, as they are not integrated into the `AITool` ecosystem.

### Option 2: Add Provider-Specific AITool-Derived Types in Provider Packages

#### Description

Create provider-specific tool types that inherit from the `AITool` abstract class within each AI provider’s package (e.g., a Foundry package could include Foundry-specific tools). The provider’s `IChatClient` implementation would natively recognize and process these `AITool`-derived types, eliminating the need for a separate registration mechanism.

#### Pros

- Integrates with the `AITool` abstract class, providing a consistent developer experience within the `Microsoft.Extensions.AI`.
- Eliminates the need for a special registration mechanism like `RawRepresentationFactory`.
- Enhances type safety and discoverability for provider-specific tools.
- Aligns with the standardized interface driver by leveraging `AITool` as the base class.

#### Cons

- Developers must know they are targeting a specific AI provider to select the appropriate `AITool`-derived types.
- Increases maintenance overhead for each provider’s package to support and update these tool types.
- Leads to fragmentation, as each provider requires its own set of `AITool`-derived types.
- Potential for duplication if multiple providers implement similar tools with different `AITool` derivatives.

### Option 3: Create Generic AITool-Derived Abstractions in M.E.AI.Abstractions

#### Description

Develop generic tool abstractions that inherit from the `AITool` abstract class in the `M.E.AI.Abstractions` package (e.g., `HostedCodeInterpreterTool`, `HostedWebSearchTool`). These abstractions map to common tool concepts across multiple AI providers, with provider-specific implementations handled internally.

#### Pros

- Provides a standardized `AITool`-based interface across AI providers, improving consistency and developer experience.
- Reduces the need for provider-specific knowledge by abstracting tool implementations.
- Highly extensible, supporting new `AITool`-derived types for common tool concepts (e.g., server-side MCP tools).

#### Cons

- Complex mapping logic needed to support diverse provider implementations.
- May not cover niche or provider-specific tools, necessitating a fallback mechanism.

### Option 4: Hybrid Approach Combining Options 1, 2, and 3

#### Description

Implement a hybrid strategy where common tools use generic `AITool`-derived abstractions in `M.E.AI.Abstractions` (Option 3), provider-specific tools (e.g., for Foundry) are implemented as `AITool`-derived types in their respective provider packages (Option 2), and rare or unsupported tools fall back to `ChatOptions.RawRepresentationFactory` (Option 1).

#### Pros

- Balances developer experience and flexibility by using the best `AITool`-based approach for each tool type.
- Supports standardized `AITool` interfaces for common tools while allowing provider-specific and breakglass mechanisms.
- Extensible and scalable, accommodating both current and future tool requirements across AI providers.
- Addresses ancillary and intermediate content (e.g., MCP permissions) with generic types.

#### Cons

- Increases complexity by managing multiple `AITool` integration approaches within the same system.
- Requires clear documentation to guide developers on when to use each option.
- Potential for inconsistency if boundaries between approaches are not well-defined.
- Higher maintenance burden to support and test multiple tool integration paths.

## More information

### AI Agent Tool Types Availability

Tool Type | Azure AI Foundry Agent Service | OpenAI Assistant API | OpenAI ChatCompletion API | OpenAI Responses API | Amazon Bedrock Agents | Google | Anthropic | Description
-- | -- | -- | -- | -- | -- | -- | -- | --
Function Calling | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Enables custom, stateless functions to define specific agent behaviors.
Code Interpreter | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | Allows agents to execute code for tasks like data analysis or problem-solving.
Search and Retrieval | ✅ (File Search, Azure AI Search) | ✅ (File Search) | ❌ | ✅ (File Search) | ✅ (Knowledge Bases) | ✅ (Vertex AI Search) | ❌ | Enables agents to search and retrieve information from files, knowledge bases, or enterprise search systems.
Web Search | ✅ (Bing Search) | ❌ | ✅ | ✅ | ❌ | ✅ (Google Search) | ✅ | Provides real-time access to internet-based content using search engines or web APIs for dynamic, up-to-date information.
OpenAPI Spec Tool | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | Integrates existing OpenAPI specifications for service APIs.
Remote MCP Servers | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ✅ | Gives the model access to new capabilities via Model Context Protocol servers.
Computer Use | ❌ | ❌ | ❌ | ✅ | ✅ (ANTHROPIC.Computer) | ❌ | ✅ | Creates agentic workflows that enable a model to control a computer interface.
Stateful Functions | ✅ (Azure Functions) | ❌ | ❌ | ❌ | ✅ (AWS Lambda) | ❌ | ❌ | Supports custom, stateful functions for complex agent actions.
Text Editor | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | Allows agents to view and modify text files for debugging or editing purposes.
Azure Logic Apps | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Low-code/no-code solution to add workflows to AI agents.
Microsoft Fabric | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Enables agents to interact with data in Microsoft Fabric for insights.
Image Generation | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | Generates or edits images using GPT image.

### API Comparison

#### Function Calling
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  Source: <a href="https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/function-calling?pivots=rest">https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/function-calling?pivots=rest</a>

  Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "function",
        "function": {
          "description": "{string}",
          "name": "{string}",
          "parameters": "{JSON Schema object}"
        }
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  {
    "tool_calls": [
      {
        "id": "{string}",
        "type": "function",
        "function": {
          "name": "{string}",
          "arguments": "{JSON object}",
        }
      }
    ]
  }
  ```
</details>
<details>
  <summary>OpenAI Assistant API</summary>
  Source: <a href="https://platform.openai.com/docs/assistants/tools/function-calling">https://platform.openai.com/docs/assistants/tools/function-calling</a>

  Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "function",
        "function": {
          "description": "{string}",
          "name": "{string}",
          "parameters": "{JSON Schema object}"
        }
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  {
    "tool_calls": [
      {
        "id": "{string}",
        "type": "function",
        "function": {
          "name": "{string}",
          "arguments": "{JSON object}",
        }
      }
    ]
  }
  ```
</details>
<details>
  <summary>OpenAI ChatCompletion API</summary>
  Source: <a href="https://platform.openai.com/docs/guides/function-calling?api-mode=chat">https://platform.openai.com/docs/guides/function-calling?api-mode=chat</a>

  Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "function",
        "function": {
          "description": "{string}",
          "name": "{string}",
          "parameters": "{JSON Schema object}"
        }
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  [
    {
      "id": "{string}",
      "type": "function",
      "function": {
        "name": "{string}",
        "arguments": "{JSON object}",
      }
    }
  ]
  ```
</details>
<details>
  <summary>OpenAI Responses API</summary>
  Source: <a href="https://platform.openai.com/docs/guides/function-calling?api-mode=responses">https://platform.openai.com/docs/guides/function-calling?api-mode=responses</a>

  Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "function",
        "description": "{string}",
        "name": "{string}",
        "parameters": "{JSON Schema object}"
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  [
    {
      "id": "{string}",
      "call_id": "{string}",
      "type": "function_call",
      "name": "{string}",
      "arguments": "{JSON object}"
    }
  ]
  ```
</details>
<details>
  <summary>Amazon Bedrock Agents</summary>
  Source: <a href="https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_CreateAgentActionGroup.html#API_agent_CreateAgentActionGroup_RequestSyntax">https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_CreateAgentActionGroup.html#API_agent_CreateAgentActionGroup_RequestSyntax</a>

  CreateAgentActionGroup Request:
  ```json
  {
    "functionSchema": {
      "name": "{string}",
      "description": "{string}",
      "parameters": {
        "type": "{string | number | integer | boolean | array}",
        "description": "{string}",
        "required": "{boolean}"
      }
    }
  }
  ```

  Tool Call Response:
  ```json
  {
    "invocationInputs": [
      {
        "functionInvocationInput": {
          "actionGroup": "{string}",
          "function": "{string}",
          "parameters": [
            {
              "name": "{string}",
              "type": "{string | number | integer | boolean | array}",
              "value": {}
            }
          ]
        }
      }
    ]
  }
  ```
</details>
<details>
  <summary>Google</summary>
  Source: <a href="https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling#rest">https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling#rest</a>

  Message Request:
  ```json
  {
    "tools": [
      {
        "functionDeclarations": [
          {
            "name": "{string}",
            "description": "{string}",
            "parameters": "{JSON Schema object}"
          }
        ]
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  {
    "content": {
      "role": "model",
      "parts": [
        {
          "functionCall": {
            "name": "{string}",
            "args": {
              "{argument_name}": {}
            }
          }
        }
      ]
    }
  }
  ```
</details>
<details>
  <summary>Anthropic</summary>
  Source: <a href="https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview">https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview</a>

  Message Request:
  ```json
  {
    "tools": [
      {
        "name": "{string}",
        "description": "{string}",
        "input_schema": "{JSON Schema object}"
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  {
    "id": "{string}",
    "model": "{string}",
    "stop_reason": "tool_use",
    "role": "assistant",
    "content": [
      {
        "type": "text",
        "text": "{string}"
      },
      {
        "type": "tool_use",
        "id": "{string}",
        "name": "{string}",
        "input": {
          "argument_name": {}
        }
      }
    ]
  }
  ```
</details>

##### Commonalities

<hr>

#### Code Interpreter
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  Source: <a href="https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/code-interpreter-samples?pivots=rest-api">https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/code-interpreter-samples?pivots=rest-api</a>

  Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "code_interpreter"
      }
    ],
    "tool_resources": {
      "code_interpreter": {
        "file_ids": ["{string}"],
        "data_sources": [
          {
            "type": {
              "id_asset": "{string}",
              "uri_asset": "{string}"
            },
            "uri": "{string}"
          }
        ]
      }
    }
  }
  ```

  Tool Call Response:
  ```json
  {
    "tool_calls": [
      {
        "id": "{string}",
        "type": "code_interpreter",
        "code_interpreter": {
          "input": "{string}",
          "outputs": [
            {
              "type": "image",
              "file_id": "{string}"
            },
            {
              "type": "logs",
              "logs": "{string}"
            }
          ]
        }
      }
    ]
  }
  ```
</details>
<details>
  <summary>OpenAI Assistant API</summary>
  Source: <a href="https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/code-interpreter-samples?pivots=rest-api">https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/code-interpreter-samples?pivots=rest-api</a>

  Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "code_interpreter"
      }
    ],
    "tool_resources": {
      "code_interpreter": {
        "file_ids": ["{string}"]
      }
    }
  }
  ```

  Tool Call Response:
  ```json
  {
    "tool_calls": [
      {
        "id": "{string}",
        "type": "code",
        "cide": {
          "input": "{string}",
          "outputs": [
            {
              "type": "logs",
              "logs": "{string}"
            }
          ]
        }
      }
    ]
  }
  ```
</details>
<details>
  <summary>OpenAI Responses API</summary>
  Source: <a href="https://platform.openai.com/docs/guides/tools-code-interpreter">https://platform.openai.com/docs/guides/tools-code-interpreter</a>

  Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "code_interpreter",
        "container": { "type": "auto" }
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  [
    {
      "id": "{string}",
      "code": "{string}",
      "type": "code_interpreter_call",
      "status": "{string}",
      "container_id": "{string}",
      "results": [
        {
          "type": "logs",
          "logs": "{string}"
        },
        {
          "type": "files",
          "files": [
            {
              "file_id": "{string}",
              "mime_type": "{string}"
            }
          ]
        }
      ]
    }
  ]
  ```
</details>
<details>
  <summary>Amazon Bedrock Agents</summary>
  Source: <a href="https://docs.aws.amazon.com/bedrock/latest/userguide/agents-enable-code-interpretation.html">https://docs.aws.amazon.com/bedrock/latest/userguide/agents-enable-code-interpretation.html</a>

  CreateAgentActionGroup Request:
  ```json
  {
    "actionGroupName": "CodeInterpreterAction",
    "parentActionGroupSignature": "AMAZON.CodeInterpreter",
    "actionGroupState": "ENABLED"
  }
  ```

  Tool Call Response:
  ```json
  {
    "trace": {
      "orchestrationTrace": {
        "invocationInput": {
          "invocationType": "ACTION_GROUP_CODE_INTERPRETER",
          "codeInterpreterInvocationInput": {
            "code": "{string}",
            "files": ["{string}"]
          }
        },
        "observation": {
          "codeInterpreterInvocationOutput": {
            "executionError": "{string}",
            "executionOutput": "{string}",
            "executionTimeout": "{boolean}",
            "files": ["{string}"],
            "metadata": {
              "clientRequestId": "{string}",
              "endTime": "{timestamp}",
              "operationTotalTimeMs": "{long}",
              "startTime": "{timestamp}",
              "totalTimeMs": "{long}",
              "usage": {
                "inputTokens": "{integer}",
                "outputTokens": "{integer}"
              }
            }
          }
        }
      }
    }
  }
  ```
</details>
<details>
  <summary>Google</summary>
  Source: <a href="https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/code-execution#googlegenaisdk_tools_code_exec_with_txt-drest">https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/code-execution#googlegenaisdk_tools_code_exec_with_txt-drest</a>

  Message Request:
  ```json
  {
    "contents": {
      "role": "{string}",
      "parts": { 
        "text": "{string}" 
      }
    },
    "tools": [
      {
        "codeExecution": {}
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  {
    "content": {
      "role": "model",
      "parts": [
        {
          "executableCode": {
            "language": "{string}",
            "code": "{string}"
          }
        },
        {
          "codeExecutionResult": {
            "outcome": "{string}",
            "output": "{string}"
          }
        }
      ]
    }
  }
  ```
</details>
<details>
  <summary>Anthropic</summary>
  [Your content here]
</details>

##### Commonalities

<hr>

#### Search and Retrieval
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  [Your content here]
</details>
<details>
  <summary>OpenAI Assistant API</summary>
  [Your content here]
</details>
<details>
  <summary>OpenAI Responses API</summary>
  [Your content here]
</details>
<details>
  <summary>Amazon Bedrock Agents</summary>
  [Your content here]
</details>
<details>
  <summary>Google</summary>
  [Your content here]
</details>

##### Commonalities

<hr>

#### Web Search
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  [Your content here]
</details>
<details>
  <summary>OpenAI ChatCompletion API</summary>
  [Your content here]
</details>
<details>
  <summary>OpenAI Responses API</summary>
  [Your content here]
</details>
<details>
  <summary>Google</summary>
  [Your content here]
</details>
<details>
  <summary>Anthropic</summary>
  [Your content here]
</details>

##### Commonalities

<hr>

#### OpenAPI Spec Tool
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  [Your content here]
</details>
<details>
  <summary>Amazon Bedrock Agents</summary>
  [Your content here]
</details>
<details>
  <summary>Google</summary>
  [Your content here]
</details>

##### Commonalities

<hr>

#### Remote MCP Servers
<details>
  <summary>OpenAI Responses API</summary>
  [Your content here]
</details>
<details>
  <summary>Google</summary>
  [Your content here]
</details>
<details>
  <summary>Anthropic</summary>
  [Your content here]
</details>

##### Commonalities

<hr>

#### Computer Use
<details>
  <summary>OpenAI Responses API</summary>
  [Your content here]
</details>
<details>
  <summary>Amazon Bedrock Agents</summary>
  [Your content here]
</details>
<details>
  <summary>Anthropic</summary>
  [Your content here]
</details>

##### Commonalities

<hr>

#### Stateful Functions
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  [Your content here]
</details>
<details>
  <summary>Amazon Bedrock Agents</summary>
  [Your content here]
</details>

##### Commonalities

<hr>

#### Text Editor
<details>
  <summary>Anthropic</summary>
  [Your content here]
</details>

##### Commonalities

<hr>

#### Azure Logic Apps
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  [Your content here]
</details>

##### Commonalities

<hr>

#### Microsoft Fabric
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  [Your content here]
</details>

##### Commonalities

<hr>

#### Image Generation
<details>
  <summary>OpenAI Responses API</summary>
  [Your content here]
</details>

##### Commonalities

<hr>

## Decision Outcome

TBD.
