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
Remote MCP Servers | ✅ | ❌ | ❌ | ✅ | ❌ | ✅ | ✅ | Gives the model access to new capabilities via Model Context Protocol servers.
Computer Use | ❌ | ❌ | ❌ | ✅ | ✅ (ANTHROPIC.Computer) | ❌ | ✅ | Creates agentic workflows that enable a model to control a computer interface.
OpenAPI Spec Tool | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | Integrates existing OpenAPI specifications for service APIs.
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

#### Commonalities

- **Standardized Tool Definition**: All providers use a JSON-based structure for defining tools, including a `type` field (commonly "function") and a `function` object with `name`, `description`, and `parameters` (often following JSON Schema).
- **Tool Call Response Structure**: Responses typically include a list of tool calls with an `id`, `type`, and details about the function called (e.g., `name` and `arguments`), enabling consistent handling of function invocations.
- **JSON Schema for Parameters**: Parameters for functions are defined using JSON Schema objects across most providers, facilitating a unified approach to parameter validation and processing.
- **Extensibility**: The structure allows for additional metadata or fields (e.g., `call_id`, `actionGroup`), suggesting potential for abstraction to support provider-specific extensions while maintaining core compatibility.

<hr>

#### Code Interpreter
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  <p>Source: <a href="https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/code-interpreter-samples?pivots=rest-api">https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/code-interpreter-samples?pivots=rest-api</a></p>

  <p>.NET Support: ✅</p>

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
  <p>Source: <a href="https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/code-interpreter-samples?pivots=rest-api">https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/code-interpreter-samples?pivots=rest-api</a></p>

  <p>.NET Support: ✅</p>

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
        "code": {
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
  <p>Source: <a href="https://platform.openai.com/docs/guides/tools-code-interpreter">https://platform.openai.com/docs/guides/tools-code-interpreter</a></p>

  <p>.NET Support: ❌ (currently in development: <a href="https://github.com/openai/openai-dotnet/issues/448">GitHub issue</a>)</p>

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
  <p>Source: <a href="https://docs.aws.amazon.com/bedrock/latest/userguide/agents-enable-code-interpretation.html">https://docs.aws.amazon.com/bedrock/latest/userguide/agents-enable-code-interpretation.html</a></p>

  <p>.NET Support: ❌ (Amazon SDK has IChatClient implementation but lacks ChatOptions.RawRepresentationFactory)</p>

  CreateAgentActionGroup Request:
  ```json
  {
    "actionGroupName": "{string}",
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
  <p>Source: <a href="https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/code-execution#googlegenaisdk_tools_code_exec_with_txt-drest">https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/code-execution#googlegenaisdk_tools_code_exec_with_txt-drest</a></p>

  <p>.NET Support: ❌ (official SDK lacks IChatClient implementation.)</p>

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
  <p>Source: <a href="https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/code-execution-tool">https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/code-execution-tool</a></p>

  <p>
  .NET Support: ❌ <br>
  <ul>
    <li><a href="https://github.com/tghamm/Anthropic.SDK">Anthropic.SDK</a> - uses `code_interpreter` instead of `code_execution` and lacks a possibility to specify file id.</li>
    <li><a href="https://github.com/tryAGI/Anthropic">Anthropic by tryAGI</a> - has `code_execution` implementation, but it's in beta and can't be used as a tool.</li>
  </ul>
  </p>

  Message Request:
  ```json
  {
    "tools": [
      {
        "name": "code_execution",
        "type": "code_execution_20250522"
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  {
    "role": "assistant",
    "container": {
      "id": "{string}",
      "expires_at": "{timestamp}"
    },
    "content": [
      {
        "type": "server_tool_use",
        "id": "{string}",
        "name": "code_execution",
        "input": {
          "code": "{string}"
        }
      },
      {
        "type": "code_execution_tool_result",
        "tool_use_id": "{string}",
        "content": {
          "type": "code_execution_result",
          "stdout": "{string}",
          "stderr": "{string}",
          "return_code": "{integer}"
        }
      }
    ]
  }
  ```
</details>

#### Commonalities

- **Tool Type Specification**: Providers consistently define a `code_interpreter` tool type within the `tools` array, indicating support for code execution capabilities.
- **Input and Output Handling**: Requests include mechanisms to specify code input (e.g., `input` or `code` fields), and responses return execution outputs, such as logs or files, in a structured format.
- **File Resource Support**: Most providers allow associating files with the code interpreter (e.g., via `file_ids` or `files`), enabling data input/output for code execution.
- **Execution Metadata**: Responses often include metadata about the execution process (e.g., `status`, `logs`, or `executionError`), which can be abstracted for standardized error handling and result processing.

<hr>

#### Search and Retrieval
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  Source: <a href="https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/file-search-upload-files?pivots=rest">https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/file-search-upload-files?pivots=rest</a>

  File Search Request:
  ```json
  {
    "tools": [
      { 
        "type": "file_search"
      }
    ],
    "tool_resources": { 
      "file_search": {
        "vector_store_ids": ["{string}"],
        "vector_stores": [
          {
            "name": "{string}",
            "configuration": {
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
        ]
      }
    }
  }
  ```

  File Search Tool Call Response:
  ```json
  {
    "tool_calls": [
      {
        "id": "{string}",
        "type": "file_search",
        "file_search": {
          "ranking_options": {
            "ranker": "{string}",
            "score_threshold": "{float}"
          },
          "results": [
            {
              "file_id": "{string}",
              "file_name": "{string}",
              "score": "{float}",
              "content": [
                {
                  "text": "{string}",
                  "type": "{string}"
                }
              ]
            }
          ]
        }
      }
    ]
  }
  ```

  Azure AI Search Request:
  ```json
  {
    "tools": [
      { 
        "type": "azure_ai_search"
      }
    ],
    "tool_resources": { 
      "azure_ai_search": {
        "indexes": [
          {
            "index_connection_id": "{string}",
            "index_name": "{string}",
            "query_type": "{string}"
          }
        ]
      }
    }
  }
  ```

  Azure AI Search Tool Call Response:
  ```json
  {
    "tool_calls": [
      {
        "id": "{string}",
        "type": "azure_ai_search",
        "azure_ai_search": {} // From documentation: Reserved for future use
      }
    ]
  }
  ```
</details>
<details>
  <summary>OpenAI Assistant API</summary>
  Source: <a href="https://platform.openai.com/docs/assistants/tools/file-search">https://platform.openai.com/docs/assistants/tools/file-search</a>

  Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "file_search"
      }
    ],
    "tool_resources": { 
      "file_search": {
        "vector_store_ids": ["string"]
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
        "type": "file_search",
        "file_search": {
          "ranking_options": {
            "ranker": "{string}",
            "score_threshold": "{float}"
          },
          "results": [
            {
              "file_id": "{string}",
              "file_name": "{string}",
              "score": "{float}",
              "content": [
                {
                  "text": "{string}",
                  "type": "{string}"
                }
              ]
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
  Source: <a href="https://platform.openai.com/docs/api-reference/responses/create">https://platform.openai.com/docs/api-reference/responses/create</a>

  Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "file_search"
      }
    ],
    "tool_resources": { 
      "file_search": {
        "vector_store_ids": ["string"]
      }
    }
  }
  ```

  Tool Call Response:
  ```json
  {
    "output": [
      {
        "id": "{string}",
        "queries": ["{string}"],
        "status": "{in_progress | searching | incomplete | failed | completed}",
        "type": "file_search_call",
        "results": [
          {
            "attributes": {},
            "file_id": "{string}",
            "filename": "{string}",
            "score": "{float}",
            "text": "{string}"
          }
        ]
      }
    ]
  }
  ```
</details>
<details>
  <summary>Amazon Bedrock Agents</summary>
  Source: <a href="https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_InvokeAgent.html">https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_InvokeAgent.html</a>

  Message Request:
  ```json
  {
    "sessionState": {
      "knowledgeBaseConfigurations": [
        { 
            "knowledgeBaseId": "{string}",
            "retrievalConfiguration": { 
               "vectorSearchConfiguration": { 
                  "filter": {},
                  "implicitFilterConfiguration": { 
                     "metadataAttributes": [ 
                        { 
                           "description": "{string}",
                           "key": "{string}",
                           "type": "{string}"
                        }
                     ],
                     "modelArn": "{string}"
                  },
                  "numberOfResults": "{number}",
                  "overrideSearchType": "{string}",
                  "rerankingConfiguration": { 
                     "bedrockRerankingConfiguration": { 
                        "metadataConfiguration": { 
                           "selectionMode": "{string}",
                           "selectiveModeConfiguration": {}
                        },
                        "modelConfiguration": { 
                           "additionalModelRequestFields": { 
                              "string" : "{JSON string}"
                           },
                           "modelArn": "{string}"
                        },
                        "numberOfRerankedResults": "{number}"
                     },
                     "type": "{string}"
                  }
               }
            }
         }
      ]
    }
  }
  ```

  Tool Call Response:
  ```json
  {
    "trace": {
      "orchestrationTrace": {
        "invocationInput": {
          "invocationType": "KNOWLEDGE_BASE",
          "knowledgeBaseLookupInput": {
            "knowledgeBaseId": "{string}",
            "text": "{string}"
          }
        },
        "observation": {
          "type": "KNOWLEDGE_BASE",
          "knowledgeBaseLookupOutput": {
            "retrievedReferences": [
              {
                "metadata": {},
                "content": {
                  "byteContent": "{string}",
                  "row": [
                    {
                      "columnName": "{string}",
                      "columnValue": "{string}",
                      "type": "{BLOB | BOOLEAN | DOUBLE | NULL | LONG | STRING}"
                    }
                  ],
                  "text": "{string}",
                  "type": "{TEXT | IMAGE | ROW}"
                }
              }
            ],
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
  Source: <a href="https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-vertex-ai-search">https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-vertex-ai-search</a>

  Message Request:
  ```json
  {
    "contents": [
      {
        "role": "user",
        "parts": [
          {
            "text": "{string}"
          }
        ]
      }
    ],
    "tools": [
      {
        "retrieval": {
          "vertexAiSearch": {
            "datastore": "{string}"
          }
        }
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
          "text": "{string}"
        }
      ]
    },
    "groundingMetadata": {
        "retrievalQueries": [
          "{string}"
        ],
        "groundingChunks": [
          {
            "retrievedContext": {
              "uri": "{string}",
              "title": "{string}"
            }
          }
        ],
        "groundingSupport": [
          {
            "segment": {
              "startIndex": "{number}",
              "endIndex": "{number}"
            },
            "segment_text": "{string}",
            "supportChunkIndices": ["{number}"],
            "confidenceScore": ["{number}"]
          }
        ]
      }
  }
  ```
</details>

#### Commonalities

- **Vector Store Integration**: Providers like Azure and OpenAI use `vector_store_ids` or similar constructs to reference vector stores for file search, suggesting a common approach to retrieval-augmented generation.
- **Search Configuration**: Requests include configurations for search (e.g., `vectorSearchConfiguration`, `ranking_options`), allowing customization of retrieval parameters like result count or ranking.
- **Result Structure**: Responses contain a list of search results with fields like `file_id`, `score`, and `content` or `text`, enabling consistent processing of retrieved data.
- **Metadata Inclusion**: Search responses often include metadata (e.g., `score`, `timestamp`, `usage`), which can be abstracted for unified analytics and performance tracking.

<hr>

#### Web Search
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  Source: <a href="https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/bing-code-samples?pivots=rest">https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/bing-code-samples?pivots=rest</a>

  Bing Search Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "bing_grounding",
        "bing_grounding": {
          "search_configurations": [
            {
              "connection_id": "{string}",
              "count": "{number}", 
              "market": "{string}", 
              "set_lang": "{string}", 
              "freshness": "{string}",
            }
          ]
        }
      }
    ]
  }
  ```

  Bing Search Tool Call Response:
  ```json
  {
    "tool_calls": [
      {
        "id": "{string}",
        "type": "function",
        "bing_grounding": {} // From documentation: Reserved for future use
      }
    ]
  }
  ```
</details>
<details>
  <summary>OpenAI ChatCompletion API</summary>
  Source: <a href="https://platform.openai.com/docs/guides/tools-web-search?api-mode=chat">https://platform.openai.com/docs/guides/tools-web-search?api-mode=chat</a>

  Message Request:
  ```json
  {
    "web_search_options": {},
    "messages": [
      {
        "role": "user",
        "content": "{string}"
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{string}",
        "annotations": [
          {
            "type": "url_citation",
            "url_citation": {
              "end_index": "{number}",
              "start_index": "{number}",
              "title": "{string}",
              "url": "{string}"
            }
          }
        ]
      }
    }
  ]
  ```
</details>
<details>
  <summary>OpenAI Responses API</summary>
  Source: <a href="https://platform.openai.com/docs/guides/tools-web-search?api-mode=responses">https://platform.openai.com/docs/guides/tools-web-search?api-mode=responses</a>

  Message Request:
  ```json
  {
    "tools": [
      {
        "type": "web_search_preview"
      }
    ],
    "input": "{string}"
  }
  ```

  Tool Call Response:
  ```json
  {
    "output": [
      {
        "type": "web_search_call",
        "id": "{string}",
        "status": "{string}"
      },
      {
        "id": "{string}",
        "type": "message",
        "status": "{string}",
        "role": "assistant",
        "content": [
          {
            "type": "output_text",
            "text": "{string}",
            "annotations": [
              {
                "type": "url_citation",
                "start_index": "{number}",
                "end_index": "{string}",
                "url": "{string}",
                "title": "{string}"
              }
            ]
          }
        ]
      }
    ]
  }
  ```
</details>
<details>
  <summary>Google</summary>
  Source: <a href="https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-search">https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-search</a>

  Message Request:
  ```json
  {
    "contents": [
      {
        "role": "user",
        "parts": [
          {
            "text": "{string}"
          }
        ]
      }
    ],
    "tools": [
      {
        "googleSearch": {}
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
          "text": "{string}"
        }
      ]
    },
    "groundingMetadata": {
      "webSearchQueries": [
        "{string}"
      ],
      "searchEntryPoint": {
        "renderedContent": "{string}"
      },
      "groundingChunks": [
        {
          "web": {
            "uri": "{string}",
            "title": "{string}",
            "domain": "{string}"
          }
        }
      ],
      "groundingSupports": [
        {
          "segment": {
            "startIndex": "{number}",
            "endIndex": "{number}",
            "text": "{string}"
          },
          "groundingChunkIndices": [
            "{number}"
          ],
          "confidenceScores": [
            "{number}"
          ]
        }
      ],
      "retrievalMetadata": {}
    }
  }
  ```
</details>
<details>
  <summary>Anthropic</summary>
  Source: <a href="https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/web-search-tool">https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/web-search-tool</a>

  Message Request:
  ```json
  {
    "tools": [
      {
        "name": "web_search",
        "type": "web_search_20250305",
        "max_uses": "{number}",
        "allowed_domains": ["{string}"],
        "blocked_domains": ["{string}"],
        "user_location": {
          "type": "approximate",
          "city": "{string}",
          "region": "{string}",
          "country": "{string}",
          "timezone": "{string}"
        }
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  {
    "role": "assistant",
    "content": [
      {
        "type": "server_tool_use",
        "id": "{string}",
        "name": "web_search",
        "input": {
          "query": "{string}"
        }
      },
      {
        "type": "web_search_tool_result",
        "tool_use_id": "{string}",
        "content": [
          {
            "type": "web_search_result",
            "url": "{string}",
            "title": "{string}",
            "encrypted_content": "{string}",
            "page_age": "{string}"
          }
        ]
      },
      {
        "text": "{string}",
        "type": "text",
        "citations": [
          {
            "type": "web_search_result_location",
            "url": "{string}",
            "title": "{string}",
            "encrypted_index": "{string}",
            "cited_text": "{string}"
          }
        ]
      }
    ]
  }
  ```
</details>

#### Commonalities

- **Tool-Based Activation**: Providers define web search as a tool (e.g., `web_search`, `bing_grounding`, `googleSearch`), typically within a `tools` array, allowing standardized activation of search capabilities.
- **Query Input**: Requests support passing a search query (e.g., via `input`, `content`, or `query`), enabling a unified interface for initiating searches.
- **Result Annotations**: Responses include search results with metadata like `url`, `title`, and sometimes `confidenceScores` or `citations`, which can be abstracted for consistent result presentation.
- **Grounding Metadata**: Most providers include grounding metadata (e.g., `groundingMetadata`, `annotations`), facilitating traceability and validation of search results.

<hr>

#### Remote MCP Servers
<details>
  <summary>OpenAI Responses API</summary>
  Source: <a href="https://platform.openai.com/docs/guides/tools-remote-mcp">https://platform.openai.com/docs/guides/tools-remote-mcp</a>

  Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "mcp",
        "server_label": "{string}",
        "server_url": "{string}",
        "require_approval": "{string}"
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  {
    "output": [
      {
        "id": "{string}",
        "type": "mcp_list_tools",
        "server_label": "{string}",
        "tools": [
          {
            "name": "{string}",
            "input_schema": "{JSON Schema object}"
          }
        ]
      },
      {
        "id": "{string}",
        "type": "mcp_call",
        "approval_request_id": "{string}",
        "arguments": "{JSON string}",
        "error": "{string}",
        "name": "{string}",
        "output": "{string}",
        "server_label": "{string}"
      }
    ]
  }
  ```
</details>
<details>
  <summary>Google</summary>
  Source: <a href="https://google.github.io/adk-docs/tools/mcp-tools/#using-mcp-tools-in-your-own-agent-out-of-adk-web">https://google.github.io/adk-docs/tools/mcp-tools/#using-mcp-tools-in-your-own-agent-out-of-adk-web</a>

  ```python
  async def get_agent_async():
  toolset = MCPToolset(
      tool_filter=['read_file', 'list_directory'] # Optional: filter specific tools
      connection_params=SseServerParams(url="http://remote-server:port/path", headers={...})
  )

  # Use in an agent
  root_agent = LlmAgent(
      model='model', # Adjust model name if needed based on availability
      name='agent_name',
      instruction='agent_instructions',
      tools=[toolset], # Provide the MCP tools to the ADK agent
  )
  return root_agent, toolset
  ```
</details>
<details>
  <summary>Anthropic</summary>
  Source: <a href="https://docs.anthropic.com/en/docs/agents-and-tools/mcp-connector">https://docs.anthropic.com/en/docs/agents-and-tools/mcp-connector</a>

  Message Request:
  ```json
  {
    "messages": [
      {
        "role": "user", 
        "content": "{string}"
      }
    ],
    "mcp_servers": [
      {
        "type": "url",
        "url": "{string}",
        "name": "{string}",
        "tool_configuration": {
          "enabled": true,
          "allowed_tools": ["{string}"]
        },
        "authorization_token": "{string}"
      }
    ]
  }
  ```

  Tool Use Response:
  ```json
  {
    "type": "mcp_tool_use",
    "id": "{string}",
    "name": "{string}",
    "server_name": "{string}",
    "input": { "param1": "{object}", "param2": "{object}" }
  }
  ```

  Tool Result Response:
  ```json
  {
    "type": "mcp_tool_result",
    "tool_use_id": "{string}",
    "is_error": "{boolean}",
    "content": [
      {
        "type": "text",
        "text": "{string}"
      }
    ]
  }
  ```
</details>

#### Commonalities

- **Server Configuration**: Providers specify remote servers via URL and metadata (e.g., `server_url`, `url`, `name`), enabling a standardized way to connect to external MCP services.
- **Tool Integration**: MCP tools are integrated into the `tools` or `mcp_servers` array, allowing agents to interact with remote tools in a consistent manner.
- **Input/Output Structure**: Requests and responses include structured input (e.g., `input`, `arguments`) and output (e.g., `output`, `content`), supporting abstraction for tool execution workflows.
- **Authorization Support**: Most providers include mechanisms for authentication (e.g., `authorization_token`, `headers`), which can be abstracted for secure communication with remote servers.

<hr>

#### Computer Use
<details>
  <summary>OpenAI Responses API</summary>
  Source: <a href="https://platform.openai.com/docs/guides/tools-computer-use">https://platform.openai.com/docs/guides/tools-computer-use</a>

  Message Request:
  ```json
  {
    "tools": [
      {
        "type": "computer_use_preview",
        "display_width": "{number}",
        "display_height": "{number}",
        "environment": "{browser | mac | windows | ubuntu}"
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  {
    "output": [
      {
        "type": "reasoning",
        "id": "{string}",
        "summary": [
          {
            "type": "summary_text",
            "text": "{string}"
          }
        ]
      },
      {
        "type": "computer_call",
        "id": "{string}",
        "call_id": "{string}",
        "action": {
          "type": "{click | double_click | drag | keypress | move | screenshot | scroll | type | wait}",
          // Other properties are associated with specific action type.
        },
        "pending_safety_checks": [],
        "status": "{in_progress | completed | incomplete}"
      }
    ]
  }
  ```
</details>
<details>
  <summary>Amazon Bedrock Agents</summary>
  Source: <a href="https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_CreateAgentActionGroup.html#API_agent_CreateAgentActionGroup_RequestSyntax">https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_CreateAgentActionGroup.html#API_agent_CreateAgentActionGroup_RequestSyntax</a><br>
  Source: <a href="https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-handle-tools.html">https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-handle-tools.html</a>

  CreateAgentActionGroup Request:
  ```json
  {
    "actionGroupName": "{string}",
    "parentActionGroupSignature": "ANTHROPIC.Computer",
    "actionGroupState": "ENABLED"
  }
  ```

  Tool Call Response:
  ```json
  {
    "returnControl": {
      "invocationId": "{string}",
      "invocationInputs": [
        {
          "functionInvocationInput": {
            "actionGroup": "{string}",
            "actionInvocationType": "RESULT",
            "agentId": "{string}",
            "function": "{string}",
            "parameters": [
              {
                "name": "{string}",
                "type": "string",
                "value": "{string}"
              }
            ]
          }
        }
      ]
    }
  }
  ```
</details>
<details>
  <summary>Anthropic</summary>
  Source: <a href="https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/computer-use-tool">https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/computer-use-tool</a>

  Message Request:
  ```json
  {
    "tools": [
      {
        "type": "computer_20250124",
        "name": "computer",
        "display_width_px": "{number}",
        "display_height_px": "{number}",
        "display_number": "{number}"
      },
    ]
  }
  ```

  Tool Call Response:
  ```json
  {
    "role": "assistant",
    "content": [
      {
        "type": "tool_use",
        "id": "{string}",
        "name": "{string}",
        "input": "{object}"
      }
    ]
  }
  ```
</details>

#### Commonalities

- **Tool Type Definition**: Providers define a computer use tool (e.g., `computer_use_preview`, `computer_20250124`, `ANTHROPIC.Computer`) within the `tools` array, indicating support for computer interaction capabilities.
- **Action Specification**: Responses include actions (e.g., `click`, `keypress`, `type`) with associated parameters, enabling standardized interaction with computer environments.
- **Environment Configuration**: Requests allow specifying the environment (e.g., `browser`, `windows`, `display_width`), which can be abstracted for cross-platform compatibility.
- **Status Tracking**: Responses include status indicators (e.g., `status`, `pending_safety_checks`), facilitating consistent monitoring of computer use tasks.

<hr>

#### OpenAPI Spec Tool
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  Source: <a href="https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/openapi-spec-samples?pivots=rest-api">https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/openapi-spec-samples?pivots=rest-api</a><br>
  Source: <a href="https://learn.microsoft.com/en-us/rest/api/aifoundry/aiagents/run-steps/get-run-step?view=rest-aifoundry-aiagents-v1&tabs=HTTP#runstepopenapitoolcall">https://learn.microsoft.com/en-us/rest/api/aifoundry/aiagents/run-steps/get-run-step?view=rest-aifoundry-aiagents-v1&tabs=HTTP#runstepopenapitoolcall</a>

  Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "openapi",
        "openapi": {
          "description": "{string}",
          "name": "{string}",
          "auth": {
            "type": "{string}"
          },
          "spec": "{OpenAPI specification object}"
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
        "type": "openapi",
        "openapi": {} // From documentation: Reserved for future use
      }
    ]
  }
  ```
</details>
<details>
  <summary>Amazon Bedrock Agents</summary>
  Source: <a href="https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_CreateAgentActionGroup.html#API_agent_CreateAgentActionGroup_RequestSyntax">https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_CreateAgentActionGroup.html#API_agent_CreateAgentActionGroup_RequestSyntax</a>

  CreateAgentActionGroup Request:
  ```json
  {
    "apiSchema": {
      "payload": "{JSON or YAML OpenAPI specification string}"
    }
  }
  ```

  Tool Call Response:
  ```json
  {
    "invocationInputs": [
      {
        "apiInvocationInput": {
          "actionGroup": "{string}",
          "apiPath": "{string}",
          "httpMethod": "{string}",
          "parameters": [
            {
              "name": "{string}",
              "type": "{string}",
              "value": "{string}"
            }
          ]
        }
      }
    ]
  }
  ```
</details>

#### Commonalities

- **OpenAPI Specification**: Both providers support defining tools using OpenAPI specifications, either as a JSON/YAML payload or a structured `spec` object, enabling standardized API integration.
- **Tool Type Identification**: The tool is identified as `openapi` or via an `apiSchema`, providing a clear entry point for OpenAPI-based tool usage.
- **Parameter Handling**: Responses include parameters (e.g., `parameters`, `apiPath`, `httpMethod`) for API invocation, which can be abstracted for unified API call execution.

<hr>

#### Stateful Functions
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  Source: <a href="https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/azure-functions-samples?pivots=rest">https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/azure-functions-samples?pivots=rest</a>

  Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "azure_function",
        "azure_function": {
          "function": {
            "name": "{string}",
            "description": "{string}",
            "parameters": "{JSON Schema object}"
          },
          "input_binding": {
            "type": "storage_queue",
            "storage_queue": {
              "queue_service_endpoint": "{string}",
              "queue_name": "{string}"
            }
          },
          "output_binding": {
            "type": "storage_queue",
            "storage_queue": {
              "queue_service_endpoint": "{string}",
              "queue_name": "{string}"
            }
          }
        }
      }
    ]
  }
  ```

  Tool Call Response: Not specified in the documentation.
</details>
<details>
  <summary>Amazon Bedrock Agents</summary>
  Source: <a href="https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_CreateAgentActionGroup.html#API_agent_CreateAgentActionGroup_RequestSyntax">https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_CreateAgentActionGroup.html#API_agent_CreateAgentActionGroup_RequestSyntax</a>

  CreateAgentActionGroup Request:
  ```json
  {
    "apiSchema": {
      "payload": "{JSON or YAML OpenAPI specification string}"
    }
  }
  ```

  Tool Call Response:
  ```json
  {
    "invocationInputs": [
      {
        "apiInvocationInput": {
          "actionGroup": "{string}",
          "apiPath": "{string}",
          "httpMethod": "{string}",
          "parameters": [
            {
                "name": "{string}",
                "type": "{string}",
                "value": "{string}"
            }
          ]
        }
      }
    ]
  }
  ```
</details>

#### Commonalities

- **API-Driven Interaction**: Both providers use API-based structures (e.g., `apiSchema`, `azure_function`) to define stateful functions, enabling integration with external services.
- **Parameter Specification**: Requests include parameter definitions (e.g., `parameters`, `JSON Schema object`), supporting standardized input handling.

<hr>

#### Text Editor
<details>
  <summary>Anthropic</summary>
  Source: <a href="https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/text-editor-tool">https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/text-editor-tool</a>

  Message Request:
  ```json
  {
    "tools": [
      {
        "type": "text_editor_20250429",
        "name": "str_replace_based_edit_tool"
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  {
    "role": "assistant",
    "content": [
      {
        "type": "tool_use",
        "id": "{string}",
        "name": "str_replace_based_edit_tool",
        "input": {
          "command": "{string}",
          "path": "{string}"
        }
      }
    ]
  }
  ```
</details>

<hr>

#### Microsoft Fabric
<details>
  <summary>Azure AI Foundry Agent Service</summary>
  Source: <a href="https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/fabric?pivots=rest">https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/fabric?pivots=rest</a>

  Message Request:
  ```json
  {
    "tools": [
      { 
        "type": "fabric_dataagent",
        "fabric_dataagent": {
          "connections": [
            {
              "connection_id": "{string}"
            }
          ]
        }
      }
    ]
  }
  ```

  Tool Call Response: Not specified in the documentation.
</details>

<hr>

#### Image Generation
<details>
  <summary>OpenAI Responses API</summary>
  Source: <a href="https://platform.openai.com/docs/guides/tools-image-generation">https://platform.openai.com/docs/guides/tools-image-generation</a>

  Message Request:
  ```json
  {
    "tools": [
      {
        "type": "image_generation"
      }
    ]
  }
  ```

  Tool Call Response:
  ```json
  {
    "output": [
      {
        "type": "image_generation_call",
        "id": "{string}",
        "result": "{Base64 string}",
        "status": "{string}"
      }
    ]
  }
  ```
</details>

<hr>

## Decision Outcome

TBD.
