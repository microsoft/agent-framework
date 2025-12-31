---
status: Proposed
contact: eavanvalkenburg
date: 2025-12-19
deciders: markwallace-microsoft, dmytrostruk, ekzhu, sphenry, giles17
consulted: taochenosu, alliscode, moonbox3, johanste, stephentoub
---

# Additional types - Computer Use and Bash Tools

## Context and Problem Statement

There are a number of capabilities that are available for chat clients that either lack a content types to accurately capture the response, or that lack a abstracted tool to allow interchangeability between chat clients. This ADR captures the proposed new types and tools, the rationale, and the alternatives considered and rejected.

For each of these, there are two decisions, the first is whether or not we need something new for it, and the second is what to call it, to make it easy these are grouped into the same considered options section. The `do nothing` option is always listed last, this is not a indication of preference either way, just a way to make it easy to see what the options are.

## Decision Drivers

- Consistent naming with current types and tools.
- Interoperability between chat clients.
- Ease of implementation and adoption.


# Computer Use

Multiple API's currently support Computer Use tools, such as OpenAI Responses [here](https://platform.openai.com/docs/guides/tools-computer-use). Claude does this as well [here](https://docs.claude.com/en/docs/agents-and-tools/tool-use/computer-use-tool)

Setup for OpenAI:
```python
{
    "type": "computer_use_preview",
    "display_width": 1024,
    "display_height": 768,
    "environment": "browser" # other possible values: "mac", "windows", "ubuntu"
}
```

Setup for claude:
```python
{
    "type": "computer_20250124",
    "name": "computer",
    "display_width_px": 1024,
    "display_height_px": 768,
    "display_number": 1,
}
```

The model then returns a call to make and it might need screenshots to be taken and sent.

One key decision is that people might expect that we also provide a local setup for this, which will be difficult to unify across platforms and providers. For the moment we will focus on just the type/tool definition. And rely on third party implementations to provide local setups, such as [CUA](https://cua.ai/), they already have a PR open for Python.

### Considered Options

1. ComputerUseTool
    - Pro: easier to use then a dict, can be extended later, and the additional_properties can be used to allow additional parameters, if those become needed.
    - Con: only available in limited number of API's currently and expectation would likely be to also include a local setup for it, which will be difficult to unify across platforms and providers. Would also require a additional Content Type
2. Nothing, allow the dict to be passed and show samples of how this works.
    - Pro: No extra effort needed.
    - Con: less discoverable, no type checking.

### Background:
**1. Tool Definitions and Parameters**
Each provider’s documentation defines a way to enable a “Computer Use” capability (often as a tool or model) and the parameters it accepts:

| **Provider** | **Tool Name / Feature** | **Key Parameters (Fields)** |
| -------------- | ---------------------- | -------------------- |
| **OpenAI**              | **Computer Use tool** (via `computer-use-preview` model) [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use), [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use) | *Tool Type*: `"computer_use_preview"`; *Display Width/Height*: e.g. `display_width=1024`, `display_height=768` (pixels); *Environment*: context of operation, e.g. `"browser"` (also supports `"mac"`, `"windows"`, `"ubuntu"`) [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use), [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use). *(No separate “name” needed in the call; the tool is included in the request’s tools list.)* |
| **Anthropic (Claude)**  | **Computer Use tool** (beta) [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool) | *Tool Type*: e.g. `"computer_20250124"` (versioned identifier for the computer-use tool) [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool); *Tool Name*: usually `"computer"` [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool); *Display Dimensions*: `display_width_px` and `display_height_px` (e.g. 1024×768) [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool); *Display Number*: e.g. `display_number=1` for primary screen [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool). *(Requires a special beta API header to enable.)* |
| **Google (Gemini API)** | **Computer Use model & tool** (Gemini 2.5 Preview) [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use)  | The Computer Use functionality is enabled by using the *Gemini 2.5 Computer-Use Preview* model together with its built-in *ComputerUse tool*. Key parameters are provided via the API config: *Environment*: e.g. `Environment.ENVIRONMENT_BROWSER` to specify a web browser context [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use); *Excluded Actions (optional)*: a list of UI actions to disallow (via `excluded_predefined_functions`) [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use). *Display size* is **not manually set**; the model internally normalizes coordinates to the screen used (recommended resolution \~1440×900, but no explicit width/height param) [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use), [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use). |
| **Amazon (Bedrock)**    | **Anthropic Claude’s Computer tool** (via Bedrock Agents) [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-create-action-group.html)                                           | Amazon Bedrock leverages Anthropic’s tool. In an agent’s action group, the tool is specified by signature `"ANTHROPIC.Computer"` with a parameter for the version/type (e.g. `"type": "computer_20241022"`) [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-create-action-group.html). There are no custom fields for display size or environment in the API call – those are handled internally or use Anthropic defaults. (Bedrock also provides Anthropic’s related tools like `ANTHROPIC.TextEditor` and `ANTHROPIC.Bash` for file and shell actions [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-computer-use.html).)  |

> **Common Parameters**: Most providers require specifying the **environment context** (e.g. browser vs. OS) and a **display/screen configuration** (resolution). OpenAI and Anthropic explicitly take screen dimensions, while Google assumes a default and normalizes coordinates. All systems implicitly handle screenshots, so an initial screenshot can often be provided (OpenAI allows an optional initial `input_image`, Anthropic and Google similarly encourage starting state input). The tool is typically identified by a type/name, often versioned for model updates. [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use)

**2. Model Response Structure (Action Requests)**
When the model decides to use the Computer Use capability, it returns a structured response indicating the action to perform (mouse movement, click, typing, etc.) rather than a normal free-form message:

| **Provider** | **Model’s Response Type** | **Description of Response Format** |
| ---------------------- | ------------------------ | ----------------- |
| **OpenAI**             | **Structured “tool call”** (`computer_call`) [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use) | The model’s response includes one or more **computer\_call items** in the output, each representing an action instruction [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use). For example, the response might contain a `ResponseComputerToolCall` object with details like `action=ActionScreenshot` or a click event and a unique `call_id`. This indicates the model is requesting an action (e.g. *“click at (x,y)”*, *“type text …”*) instead of providing a final answer. The response is not free-form text but a structured object in the API payload that your code must intercept and act upon. |
| **Anthropic (Claude)** | **Tool Use invocation** (`stop_reason: "tool_use"`) [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool) | Claude’s response indicates it’s attempting a tool action by returning a special message with `stop_reason` set to `"tool_use"` [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool). The content of the message includes a **`tool_use` block** that specifies the tool name (e.g. `"computer"`) and an **action with parameters** (such as `"action": "left_click", "coordinate": [x,y]`, or `"action": "type", "text": "…"`). This is a structured JSON-like content inside Claude’s response. Essentially, Claude stops its normal reply and asks for the tool to be executed with the given parameters [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool), [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool). |
| **Google (Gemini)**    | **JSON Function Call** (`function_call`) [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use)  | The Gemini Computer Use model responds with a **FunctionCall object** in the JSON payload whenever it wants to perform a UI action [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use). The response message includes `function_call.name` (e.g. `"click_at"` or `"type_text_at"`) and `args` (arguments like coordinates and text) [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use). Multiple actions can even be returned in parallel (as separate function calls in one response) [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use). Google’s response may also include a `safety_decision` field indicating if the action needs user confirmation for safety [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use). Overall, the model’s output is a structured JSON with the intended function to execute, not conversational text. |
| **Amazon (Bedrock)**   | **Structured Tool Request** (`returnControl` payload) [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-handle-tools.html), [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-handle-tools.html) | In Bedrock Agents, when Claude (running via Bedrock) decides to use the computer tool, the InvokeAgent response contains a **`returnControl` JSON** with the tool and action. For example, `returnControl.invocationInputs[0].functionInvocationInput` will specify `"function": "computer"` and parameters like `"action": "screenshot"` or `"mouse_move"` [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-handle-tools.html), [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-handle-tools.html). This structured payload is how Bedrock signals that the agent is asking for a computer action. The format is JSON (nested in the response), not a normal message string. |

> **Commonalities**: All providers use a **structured schema** for action requests. Instead of the model replying with prose, it produces a machine-readable instruction: OpenAI in its Responses API returns a `computer_call` object, Anthropic uses a `tool_use` content block with a JSON action, Google uses the formal function\_call mechanism, and AWS’s Bedrock also yields a JSON payload. In each case, the model’s intent to click/type is encoded in a standard format (not plain text), which includes the action name and parameters (like coordinates or text to enter). This consistency means the response is **not free-form** – the developer’s code can reliably parse the needed action.

**3. Tool Output and Return Types**
After executing the instructed action on the real or virtual machine, the developer must send the **result** back to the model. The expected format for these results is also structured:

| **Provider** | **Returning the Tool’s Output**  | **Format of Return Data** |
| -------- | ------ | ------------- |
| **OpenAI**             | **Computer Call Output** (`computer_call_output`) [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use), [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use)                                              | The OpenAI Responses API expects the developer to **return a screenshot or result** of the action in the next request as a `computer_call_output`. This is done by including an input of type `"input_image"` (for screenshots) or other relevant types in the follow-up call [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use), [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use). Essentially, you capture the state (usually a PNG image of the screen after the click/typing) and send it back in the API call, tied to the `call_id` of the action. The model will then analyze this image in the next loop iteration. The data is sent in a structured way (e.g., base64-encoded image in JSON) rather than as plain text. |
| **Anthropic (Claude)** | **Tool Result Message** (`tool_result` content block) [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool) | Claude expects the tool’s outcome returned as a special message in the conversation. The developer sends a new user-turn message whose content has type `"tool_result"`, referencing the original tool use ID and providing the result [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool). For a screenshot action, this content would include the image (encoded as binary/base64 data) and perhaps metadata. In code, Anthropic’s reference implementation returns, for example, an image’s bytes in the `content` field of the tool\_result [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-handle-tools.html). The format is JSON structure: e.g. `{type: "tool_result", tool_use_id: "...", content: {…result data…}}`. This structured result is then fed back into Claude, rather than a text description. |
| **Google (Gemini)**    | **FunctionResponse objects** [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use), [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use) | Google’s API requires the results of each action to be sent back via **FunctionResponse** entries. After executing an action, the developer creates a `FunctionResponse` with the same function name and attaches the outcome: typically this includes a screenshot (binary image data) and the current page URL [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use), [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use). In practice, the return is a JSON payload where the image is included as an `inline_data` blob (e.g., PNG bytes) [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use). The model will then ingest this structured data as the outcome of the function call. No free-form text is used here – the screenshot and any other info (like a confirmation that typing is done or a new page URL) are packed into the structured response object. |
| **Amazon (Bedrock)**   | **InvokeAgent with Result Data** [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-handle-tools.html), [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-handle-tools.html) | In Bedrock, after performing the action, the developer calls `InvokeAgent` again, supplying the results in the request. The Bedrock docs provide a code sample where after a screenshot action, they prepare a result dict containing the image bytes (in a field `"IMAGES"` with format and byte data) [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-handle-tools.html). This is sent back to the agent in the next invocation so Claude can process it. The format is structured JSON matching what the agent expects – for a screenshot, a list of images with their binary data and metadata [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-handle-tools.html). Similarly, outputs of other actions (like text from the TextEditor or stdout from Bash) are returned in JSON form. Essentially, the result is **not** just printed or described; it’s delivered as data in a predefined schema (following Anthropic’s tool interface conventions). |

> **Common Return Format**: Across providers, the tool’s output (especially screenshots) is returned in a **machine-readable JSON structure** rather than as open text. Typically this means encoding images (usually PNG) in base64 within the API call’s payload or object, along with any identifiers. All platforms enforce this structured loop: the model asks for an action, the developer executes it and **returns a structured result** (image or data), which the model then uses for the next step. This ensures a universal pattern: *action requests in JSON, and action results in JSON*. The use of images/screenshots is central to “Computer Use” – every provider includes screenshot data as a return type (OpenAI and Google explicitly use images, Anthropic/AWS do the same via bytes in JSON). The consistency is that the **return type is not free-form text**; it’s typically a JSON object or list (often containing an image blob, or other structured info like updated URLs or confirmation flags) that the AI agent will interpret in the next iteration. [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use), [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use)

**Sources:** The information above is based on the official developer documentation and guides for each provider’s AI agent tool interface: OpenAI’s Tools/Responses API documentation, Anthropic’s Claude tool use guide, Mistral’s Agents API documentation and third-party explanations, Google’s Gemini API documentation for Computer Use, and Amazon Bedrock’s user guide for computer use tool integration. Each of these references provides more detailed schemas and examples. [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use), [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-computer-use) [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool), [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool), [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use), [\[ai.google.dev\]](https://ai.google.dev/gemini-api/docs/computer-use) [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-create-action-group.html), [\[docs.aws.amazon.com\]](https://docs.aws.amazon.com/bedrock/latest/userguide/agent-computer-use-handle-tools.html)


### Decision Outcome

1. **ComputerUseTool** - A hosted tool abstraction for computer use capabilities.

## ComputerUseTool Design

The `ComputerUseTool` allows users to enable computer use capabilities across multiple providers with a consistent interface.

```python
class ComputerUseTool(BaseTool):
    """Represents a computer use tool that enables AI models to interact with a computer interface.

    Attributes:
        display_width: Optional width of the display in pixels.
        display_height: Optional height of the display in pixels.
        environment: The environment context (e.g., "browser", "mac", "windows", "linux").
    """

    def __init__(
        self,
        *,
        display_width: int | None = None,
        display_height: int | None = None,
        environment: Literal["browser", "mac", "windows", "linux"] | str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        ...
```

### Field Mapping

| Generic Field     | OpenAI Field         | Anthropic Field       | Google Field           | Notes                                          |
| ----------------- | -------------------- | --------------------- | ---------------------- | ---------------------------------------------- |
| `display_width`   | `display_width`      | `display_width_px`    | N/A (auto-detected)    | Width in pixels (optional)                     |
| `display_height`  | `display_height`     | `display_height_px`   | N/A (auto-detected)    | Height in pixels (optional)                    |
| `environment`     | `environment`        | N/A                   | `Environment` enum     | Execution context (browser, OS, etc.)          |

> **Note**: Provider-specific fields like Anthropic's `display_number` should be passed via `additional_properties`.

### Usage Example

```python
from agent_framework import ComputerUseTool

tools = [
    get_weather,
    HostedCodeInterpreterTool(),
    # With explicit dimensions
    ComputerUseTool(display_width=1920, display_height=1080, environment="browser"),
    # Or with defaults (provider-specific)
    ComputerUseTool(environment="linux"),
    # With Anthropic-specific display_number via additional_properties
    ComputerUseTool(display_width=1024, display_height=768, additional_properties={"display_number": 1}),
]
```

## ComputerUseCallContent Design

The `ComputerUseCallContent` represents an action request from the model to perform a computer interaction (click, type, screenshot, etc.).

```python
class ComputerUseAction(str, Enum):
    """Represents the types of computer actions that can be requested."""
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    TRIPLE_CLICK = "triple_click"
    MOVE = "move"
    DRAG = "drag"
    TYPE = "type"
    KEY = "key"
    SCREENSHOT = "screenshot"
    SCROLL = "scroll"
    WAIT = "wait"
    ZOOM = "zoom"

class ComputerUseCallContent(BaseContent):
    """Represents a computer action request from the model.

    Attributes:
        call_id: The unique identifier for this computer call (for correlating with results).
        action: The type of action to perform.
        coordinate: The (x, y) coordinate for the action, if applicable.
        end_coordinate: The end (x, y) coordinate for drag actions.
        text: Text to type, if applicable.
        key: Key or key combination to press (e.g., "Enter", "ctrl+c").
        button: Mouse button for click actions (left, right, middle).
            Should be combined with a click action.
        scroll_amount: Amount to scroll (positive = down/right, negative = up/left).
        scroll_direction: Direction for scrolling ("vertical", "horizontal").
        duration: Duration in milliseconds for wait actions.
        type: The type of content, always "computer_call" for this class.
    """

    def __init__(
        self,
        *,
        call_id: str,
        action: ComputerUseAction | str,
        coordinate: tuple[int, int] | None = None,
        end_coordinate: tuple[int, int] | None = None,
        text: str | None = None,
        key: str | None = None,
        button: Literal["left", "right", "middle"] | None = None,
        scroll_amount: int | None = None,
        scroll_direction: Literal["vertical", "horizontal"] | None = None,
        duration: int | None = None,
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        ...
        self.type: Literal["computer_call"] = "computer_call"
```

### Field Mapping for ComputerUseCallContent

| Generic Field            | OpenAI Field            | Anthropic Field        | Google Field             | Notes                                      |
| ------------------------ | ----------------------- | ---------------------- | ------------------------ | ------------------------------------------ |
| `call_id`                | `call_id`               | `id` (tool_use block)  | N/A (function call id)   | Unique identifier for correlation          |
| `action`                 | `action` type           | `action`               | `function_call.name`     | The action type                            |
| `coordinate`             | `x`, `y`                | `coordinate`           | `args.x`, `args.y`       | Position for mouse actions                 |
| `end_coordinate`         | `end_x`, `end_y`        | N/A                    | `args.end_x`, `args.end_y` | End position for drag operations         |
| `text`                   | `text`                  | `text`                 | `args.text`              | Text to type                               |
| `key`                    | `key`                   | `key`                  | `args.key`               | Key or key combo to press                  |
| `button`                 | `button`                | action: `CLICK` & button=`left`-> `left_click` action   | `args.button`            | Mouse button                               |
| `scroll_amount`          | `scroll_x`/`scroll_y`   | `scroll_amount`        | `args.amount`            | Scroll distance                            |

## ComputerUseResultContent Design

The `ComputerUseResultContent` represents the result of executing a computer action, typically containing a screenshot and optional metadata.

```python
class ComputerUseResultContent(BaseContent):
    """Represents the result of a computer action execution.

    The result typically includes a screenshot of the screen state after the action,
    along with optional error information.

    Attributes:
        call_id: The identifier of the computer call for which this is the result.
        screenshot: The screenshot data as DataContent (image/png typically).
        text_output: Optional text output from the action (e.g., clipboard content, OCR result).
        error: Error message if the action failed.
        type: The type of content, always "computer_result" for this class.
    """

    def __init__(
        self,
        *,
        call_id: str,
        screenshot: DataContent | None = None,
        text_output: TextContent | str | None = None,
        error: str | None = None,
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        ...
        self.type: Literal["computer_result"] = "computer_result"
```

### Field Mapping for ComputerUseResultContent

| Generic Field     | OpenAI Field                 | Anthropic Field                      | Google Field                  | Notes                                        |
| ----------------- | ---------------------------- | ------------------------------------ | ----------------------------- | -------------------------------------------- |
| `call_id`         | `call_id`                    | `tool_use_id`                        | (function response name)      | Correlates with the original call            |
| `screenshot`      | `input_image` (base64)       | `content` (image bytes)              | `inline_data` (PNG blob)      | Screenshot as `DataContent`                  |
| `text_output`     | N/A                          | `content` (text result)              | N/A                           | Text result as `TextContent` or string       |
| `error`           | (in additional_properties)   | `is_error`, `content`                | (error in response)           | Error message if action failed               |

> [!Note]
> OpenAI uses `pending_safety_checks` to warn users of potentially unsafe actions. This should probably result in a FunctionCallApprovalRequestContent being created to allow user approval before proceeding, we should adapt that class to also support ComputerCallContent instead of only FunctionCallContent.

### Usage Example

```python
from agent_framework import ComputerUseCallContent, ComputerUseResultContent, ComputerUseAction, DataContent, TextContent

# Processing a computer call from the model
for content in response.content:
    if isinstance(content, ComputerUseCallContent):
        # Execute the action locally or via CUA/other implementation
        screenshot_bytes = execute_computer_action(content)

        # Create the result to send back
        result = ComputerUseResultContent(
            call_id=content.call_id,
            screenshot=DataContent(data=screenshot_bytes, media_type="image/png"),
        )

        # Or with text output
        result_with_text = ComputerUseResultContent(
            call_id=content.call_id,
            screenshot=DataContent(data=screenshot_bytes, media_type="image/png"),
            text_output=TextContent(text="Clipboard content: Hello World"),
        )

        # Or with an error
        error_result = ComputerUseResultContent(
            call_id=content.call_id,
            error="Failed to click: coordinates out of bounds",
        )
```

### Design Rationale

1. **Leverages existing types**: `DataContent` is used for screenshots (binary image data), and `TextContent` can be used for text outputs, maintaining consistency with the framework.

2. **Generic field names**: Fields like `coordinate` instead of provider-specific `x`/`y` or `coordinate` allow for consistent usage while the field mapping table documents how these translate to each provider.

3. **Extensibility**: The `additional_properties` field (inherited from `BaseContent`) allows passing provider-specific fields that aren't covered by the generic interface.

4. **Safety considerations**: The `pending_safety_review` field allows capturing Google's safety decision mechanism and can be used to implement approval workflows.

5. **Error handling**: Explicit `error` field in results allows distinguishing between successful actions with screenshots and failed actions.


# Bash or Shell

Multiple API's currently support Bash or Shell tools, such as OpenAI Responses [here](https://platform.openai.com/docs/api-reference/responses/create#responses-create-tools). And Anthropic Claude [here](https://docs.claude.com/en/docs/agents-and-tools/tool-use/bash-tool).

They work by having a local bash session which is fed with commands to execute, and the output is returned to the agent, for instance for Claude, the commands are `command` or `restart`.

To setup for Claude:
```json
{
    "type": "bash_20250124",
    "name": "bash"
}
```

and for OpenAI:
```json
{
    "type": "shell"
}
```

The commands should then be taken and executed with the local shell session. In OpenAI Agents SDK this is built in, with something called the `LocalShellExecutor`, and all coding agents also leverage a shell call, usually in a sandboxed environment.

The bash and computer use tools are often used in conjunction to allow more control over a local machine.

### Considered Options

1. ShellTool
    - Pro: easier to use then a dict, can be extended later, and the additional_properties can be used to allow additional parameters, if those become needed.
    - Con: only available in limited number of API's currently and expectation would likely be to also include a local setup for it, which will be difficult to unify across platforms and providers. Would also require a additional Content Type
    - Alternative names: ShellTool, LocalShellTool, LocalBashTool
2. Nothing, allow the dict to be passed and show samples of how this works.
    - Pro: No extra effort needed.
    - Con: less discoverable, no type checking.

#### Background
### Tool Definitions

| Provider      | Shell/Bash Tool Implementation & Key Parameters  |
| ------------- | --------------- |
| **OpenAI**    | **Shell tool** (via Responses API): Provided by setting `"tools": [{"type": "shell"}]` in the request [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-shell). The model can propose commands to run. When it decides to use the shell, the response includes a `shell_call` object. Key fields include a list of `commands` to execute, optional `timeout_ms`, and `max_output_length` for truncation [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-shell). (Older Codex models used a similar `local_shell` tool, now superseded by the `shell` tool [\[platform.openai.com\]](https://platform.openai.com/docs/guides/tools-local-shell).) The tool doesn’t require specifying arguments upfront beyond adding it to the tools list; the model dynamically populates the command(s). |
| **Anthropic** | **Bash tool** (Claude Agents API): Included by adding `{ "type": "bash_<version>", "name": "bash" }` to the tools array [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/bash-tool) (e.g. `bash_20250124` for Claude 4). Claude’s prompt output will contain a **tool use** request with a JSON input. Key parameters are `command` (the shell command string to run) and an optional `restart` flag to reset the persistent session [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/bash-tool). The bash tool maintains state between commands (working directory, environment variables, etc.) across multiple calls [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/bash-tool). No custom schema is needed as it’s built-in; the model knows how to format the tool call. |
| **Google**    | **Gemini CLI (Google Codey/Gemini)**: Google’s Gemini Code Assist agent includes a built-in **Shell/Terminal tool** for executing commands. In the IDE agent settings, this is referred to as `"ShellTool"` (the tool for terminal commands) [\[developers...google.com\]](https://developers.google.com/gemini-code-assist/docs/use-agentic-chat-pair-programmer#configure-mcp-servers). Developers don’t manually define parameters for built-in tools – the agent can call the terminal with a command string. The Gemini CLI uses a ReAct loop, where the model’s plan will include an action like using the Terminal tool with a specific command. Configuration allows whitelisting specific commands (e.g., only allow `ShellTool(ls -l)`) or blacklisting certain commands (e.g. block `ShellTool(rm -rf)`) [\[developers...google.com\]](https://developers.google.com/gemini-code-assist/docs/use-agentic-chat-pair-programmer#configure-mcp-servers). This implies the shell tool’s primary parameter is the command text (with potential internal options for safety).  |
| **Amazon**    | **Bedrock Agent actions**: Amazon Bedrock’s AgentCore doesn’t surface a single “shell tool” in documentation; instead, it lets developers integrate external tools or actions (e.g., via AWS Lambda functions or API calls). To run shell operations, a developer could create a custom action (for example, a Lambda that executes a command) and include it in the agent’s allowed tools. Bedrock AgentCore emphasizes *policy definitions* to constrain tools: using natural-language rules to allow or forbid certain actions or commands [\[aboutamazon.com\]](https://www.aboutamazon.com/news/aws/aws-amazon-bedrock-agent-core-ai-agents). Thus, while there isn’t a predefined “bash tool,” the platform supports similar use cases through custom **Agent Actions**. Key parameters would depend on the custom integration (e.g., a “RunCommand” action might take a `command` string and perhaps a `workingDirectory`), governed by policies.  |

### Return Types

| Provider      | How Shell Command Output Is Returned to the AI Model |
| --------- | ----- |
| **OpenAI**    | The output of executed shell commands is returned via a special message in the API. The model’s response includes a `"shell_call"` request with a `call_id`; the developer executes the command(s) and then sends back a `"shell_call_output"` item containing the results. Each shell\_call\_output includes fields for `stdout` (captured standard output text), `stderr` (captured error output), and an `outcome` status indicator (e.g. `"success"` or `"timeout"`/error). These outputs are raw text streams. The OpenAI Responses API handles this in a loop: the model may issue multiple shell\_call requests and incorporate each returned output into its next reasoning step. Ultimately, the final answer the model gives the user is composed after all needed outputs are gathered.  |
| **Anthropic** | In Claude’s tool-use paradigm, when Claude uses the bash tool, the client executes the command and returns a **tool result message**. This is typically structured as a message of type `"tool_result"` with a reference to the original tool use call (`tool_use_id`) and the content containing the command’s output [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/bash-tool). The output content is usually a text blob combining stdout and stderr (the Claude Code implementation reads both and returns them together unless handled separately). Essentially, Claude receives the command’s result as plain text in the `content` field of the tool\_result. Claude can then incorporate that text into its next assistant reply. There isn’t a separate JSON schema for output; it’s treated as free-form text result (the model itself may sometimes prepend something like "Output:\n" or similar, but generally the raw output is provided).                                                                                                                                                                               |
| **Google**    | In Google’s Gemini CLI agent, when the model uses the terminal tool, the output from the shell is captured and displayed to the user, but from the model’s perspective, it’s handled as an action result. Internally, the agent executes the command and then feeds the console output back into the conversation loop. The exact structure isn’t public, but it’s analogous to others: the agent likely treats the terminal output as a chunk of text. In the VS Code/IDE integration, the agent will show the command’s output (stdout/stderr) in-line in the chat or terminal panel. There’s no special JSON schema visible to developers; it’s abstracted. We do know Gemini’s agent mode can incorporate tool outputs as context for the next prompt [\[developers...google.com\]](https://developers.google.com/gemini-code-assist/docs/use-agentic-chat-pair-programmer#configure-mcp-servers). So effectively, the return “type” is text (the console output), which the agent can then reason on or present. If the tool fails or produces an error code, the agent would include that message (there might be conventions like prefixing with “Error:” if non-zero exit). |
| **Amazon**    | Amazon Bedrock AgentCore returns tool outputs in the format defined by each **Agent Action**. For example, if using a Lambda to run a shell command, that Lambda might return a JSON with fields like `stdout` and `stderr`, or just a combined text output. The Bedrock agent will take that and feed it into the model’s context. Bedrock’s agent schemas allow defining the action’s output structure (e.g., an action could have an output schema with properties for result text or data). In general, for simple shell tasks we’d expect a textual output or a structured result containing the command’s output and exit status. The key commonality is that the output is captured and provided back to the model before it continues the conversation. (Official Bedrock docs emphasize the agent’s ability to receive the outcome of tool calls but do not prescribe a single format for “shell” results since it’s user-defined in each action.)  |

### Response Structure

| Provider      | How the Assistant Structures and Presents Shell Execution Results in Responses                                                                       |
| -------- | ------- |
| **OpenAI**    | With OpenAI’s function calling approach, the model initially produces a function (tool) call instead of a direct answer. After the shell tool is executed and the `shell_call_output` is provided, the model will then generate an **assistant message** that uses the command’s output to answer the user. The developer doesn’t have to manually format the output for the user; the model typically incorporates it into a final answer. For example, if the user asked to list files, the final assistant message might include a code block or a quoted list of filenames as returned by `ls`. The OpenAI docs don’t mandate a specific format for presenting shell results – it depends on the prompt and the model’s style. However, since the model is aware it’s returning terminal output, it may often use markdown syntax (e.g. markdown code blocks for multi-line outputs) when appropriate. The structure is thus dynamic: the sequence is user -> (assistant calls shell tool) -> (tool output) -> assistant completes answer (which may quote or format the shell output). This mechanism is internal; from the end-user perspective, they simply see the assistant’s final answer, which includes the command’s results possibly formatted as text or a code snippet.                                                                                                                                                                  |
| **Anthropic** | In Claude’s case, when the bash tool executes, Claude receives the output text and then continues the conversation. Typically, Claude will include the results in a coherent way in its next message. If the output is short, it might be inlined; if it’s longer or more technical, Claude might present it in a markdown code block or as a quoted text block. The **Claude Code** interface historically would show command outputs distinctly, requiring user approval for each step, but with the new sandboxed bash tool, Claude can output results directly without interrupting for permission [\[anthropic.com\]](https://www.anthropic.com/engineering/claude-code-sandboxing), [\[anthropic.com\]](https://www.anthropic.com/engineering/claude-code-sandboxing). The structure of the response is thus a normal assistant message possibly containing portions of the shell’s output. There’s no special tagging of the output in the final answer (e.g., no JSON), just natural language and perhaps fenced code. Anthropic’s docs point out that Claude can chain commands and use their outputs in subsequent steps [\[platform.claude.com\]](https://platform.claude.com/docs/en/agents-and-tools/tool-use/bash-tool), meaning the assistant’s reply will reflect any findings from those commands in a seamless narrative or answer format.                                             |
| **Google**    | Google’s Gemini CLI tries to mimic a developer’s terminal assistant. The **response structure** in agent mode often involves the model explaining or confirming actions, and the actual command output displayed possibly in a segregated format. In VS Code’s agent chat, for instance, when the agent runs a terminal command, the output appears in the chat prefixed by the tool’s name or as a block. The documentation indicates that the agent will “request permission to use a tool” and then after execution, the changes/results are shown, with the user having a chance to review [\[developers...google.com\]](https://developers.google.com/gemini-code-assist/docs/use-agentic-chat-pair-programmer#configure-mcp-servers). If auto-approved, it just executes and shows output. So, the structure might be something like: *Assistant:* “Running `make build`...”, followed by a block of output lines. Google’s tools thus integrate the shell output within the assistant’s message flow. They caution that there’s no undo, so the agent might also describe what it did (e.g., “Output of the command is above. Build succeeded.”). In summary, Gemini’s agent will present shell outputs as part of the chat, often as raw text or formatted as needed (with no extra JSON). This is consistent with the pattern across providers: outputs are shown as text (sometimes in code blocks) in the assistant’s reply. |
| **Amazon**    | Amazon’s Bedrock AgentCore delegates much of the response formatting to the developer or the agent implementation. Given an agent action for a shell command, the developer could decide to have the agent respond with something like: “Command executed. Output:\n`\n<output here>\n`”. Bedrock’s focus on enterprise control means the agent’s responses might also include additional context or confirmations. The **AgentCore** system supports *“Agent Replies”* that incorporate tool results. For instance, after a custom “ExecuteShell” action returns output, the agent’s next message to the user might say, *“I ran the command. Here is the output:”* followed by the output text. There’s no strict or universal format enforced by Amazon; instead, agents are expected to respond helpfully using the data. Common practice would align with others – printing command outputs plainly or in code formatting. Notably, Amazon’s policy system might strip or refuse to include certain content in the response if it violates rules, but assuming it’s safe, it will be included directly.


### Decision Outcome

1. **ShellTool** - A hosted tool abstraction for shell/bash execution capabilities.

## ShellTool Design

The `ShellTool` allows users to enable shell execution capabilities across multiple providers with a consistent interface.

```python
class ShellTool(BaseTool):
    """Represents a shell/bash tool that enables AI models to execute shell commands."""

    def __init__(
        self,
        *,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        ...
```

> **Note**: Provider-specific fields should be passed via `additional_properties`.

### Usage Example

```python
from agent_framework import ShellTool

tools = [
    get_weather,
    HostedCodeInterpreterTool(),
    ShellTool(),
]
```

## ShellCallContent Design

The `ShellCallContent` represents a shell command execution request from the model.

```python
class ShellAction(str, Enum):
    """Represents the types of shell actions that can be requested."""
    EXECUTE = "execute"
    RESTART = "restart"

class ShellCallContent(BaseContent):
    """Represents a shell command execution request from the model.

    Attributes:
        call_id: The unique identifier for this shell call (for correlating with results).
        action: The type of action to perform (execute command or restart session).
        commands: The shell commands to execute.
        type: The type of content, always "shell_call" for this class.
    """

    def __init__(
        self,
        *,
        call_id: str,
        action: ShellAction | str = ShellAction.EXECUTE,
        commands: list[str] | None = None,
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        ...
        self.type: Literal["shell_call"] = "shell_call"
```

### Field Mapping for ShellCallContent

| Generic Field         | OpenAI Field          | Anthropic Field       | Google Field          | Notes                                          |
| --------------------- | --------------------- | --------------------- | --------------------- | ---------------------------------------------- |
| `call_id`             | `call_id`             | `id` (tool_use block) | N/A (function call id)| Unique identifier for correlation              |
| `action`              | N/A (implicit)        | `restart` flag        | N/A                   | Execute or restart session                     |
| `commands`            | `commands`            | `command` (string)    | command argument      | The commands to execute                        |

> **Note**: Anthropic uses a single command string. When mapping from Anthropic, wrap the command in a list. When mapping to Anthropic, join commands or send sequentially.

## ShellResultContent Design

The `ShellResultContent` represents the result of executing a shell command, leveraging `TextContent` for output streams.

```python
class ShellOutcome(str, Enum):
    """Represents the outcome of a shell command execution."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

class ShellResultContent(BaseContent):
    """Represents the result of a shell command execution.

    The result includes stdout, stderr, exit code, and outcome status.
    Uses TextContent for the output streams to maintain consistency with other framework types.

    Attributes:
        call_id: The identifier of the shell call for which this is the result.
        stdout: The standard output from the command as TextContent or string.
        stderr: The standard error output from the command as TextContent or string.
        exit_code: The exit code of the command (0 typically indicates success).
        outcome: The outcome status of the execution.
        type: The type of content, always "shell_result" for this class.
    """

    def __init__(
        self,
        *,
        call_id: str,
        stdout: TextContent | str | None = None,
        stderr: TextContent | str | None = None,
        exit_code: int | None = None,
        outcome: ShellOutcome | str = ShellOutcome.SUCCESS,
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        ...
        self.type: Literal["shell_result"] = "shell_result"
```

### Field Mapping for ShellResultContent

| Generic Field     | OpenAI Field                 | Anthropic Field                      | Google Field                  | Notes                                        |
| ----------------- | ---------------------------- | ------------------------------------ | ----------------------------- | -------------------------------------------- |
| `call_id`         | `call_id`                    | `tool_use_id`                        | (function response name)      | Correlates with the original call            |
| `stdout`          | `stdout`                     | `content` (combined output)          | (text result)                 | Standard output as `TextContent` or string   |
| `stderr`          | `stderr`                     | `content` (combined output)          | (text result)                 | Standard error as `TextContent` or string    |
| `exit_code`       | (in outcome)                 | N/A                                  | N/A                           | Command exit code                            |
| `outcome`         | `outcome`                    | `is_error`                           | (error in response)           | Execution outcome status                     |

> **Note**: Anthropic typically combines stdout and stderr into a single `content` field. When receiving from Anthropic, implementations may need to set both to the same value or parse the combined output.

### Usage Example

```python
from agent_framework import ShellCallContent, ShellResultContent, ShellAction, ShellOutcome, TextContent
import subprocess

# Processing a shell call from the model
for content in response.content:
    if isinstance(content, ShellCallContent):
        if content.action == ShellAction.RESTART:
            # Restart the shell session (no exit_code - no command executed)
            result = ShellResultContent(
                call_id=content.call_id,
                stdout=TextContent(text="Shell session restarted."),
                outcome=ShellOutcome.SUCCESS,
            )
        else:
            # Execute the commands
            try:
                cmd = " && ".join(content.commands) if content.commands else ""
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                )
                result = ShellResultContent(
                    call_id=content.call_id,
                    stdout=TextContent(text=proc.stdout) if proc.stdout else None,
                    stderr=TextContent(text=proc.stderr) if proc.stderr else None,
                    exit_code=proc.returncode,
                    outcome=ShellOutcome.SUCCESS if proc.returncode == 0 else ShellOutcome.ERROR,
                )
            except Exception as e:
                # No exit_code - command failed to execute
                result = ShellResultContent(
                    call_id=content.call_id,
                    stderr=TextContent(text=str(e)),
                    outcome=ShellOutcome.ERROR,
                )

        # Or with string shortcuts (converted internally)
        simple_result = ShellResultContent(
            call_id=content.call_id,
            stdout="Command output here",
            exit_code=0,
            outcome=ShellOutcome.SUCCESS,
        )
```

### Design Rationale

1. **Leverages existing types**: `TextContent` is used for stdout/stderr outputs, maintaining consistency with the framework. String shortcuts are also allowed for convenience.

2. **Standardized on `commands`**: Uses `list[str]` to align with OpenAI's format. When mapping from Anthropic (single command string), wrap in a list.

3. **Extensibility**: The `additional_properties` field (inherited from `BaseContent`) allows passing provider-specific fields that aren't covered by the generic interface.

4. **Session management**: The `ShellAction.RESTART` action supports Anthropic's session restart capability while being optional for providers that don't support it.

5. **Rich outcome information**: The `ShellOutcome` enum captures various execution states (success, error, timeout, cancelled), and the explicit `exit_code` field provides the actual command return code.

---

> [!IMPORTANT]
> **This framework does NOT provide implementations of computer use or shell tools.**
>
> The types defined in this document (`ComputerUseTool`, `ComputerUseCallContent`, `ComputerUseResultContent`, `ShellTool`, `ShellCallContent`, `ShellResultContent`) are **abstractions only**. They exist solely to normalize the differences between providers (OpenAI, Anthropic, Google, etc.) and give developers building computer use or shell sandboxes an easier time creating cross-provider solutions.
>
> **If you intend to implement computer use or shell execution capabilities, you must:**
>
> - Carefully consider the security implications and attack surface
> - Implement appropriate sandboxing, isolation, and access controls
> - Limit the scope of what commands or actions can be executed
> - Monitor and log all actions for auditing purposes
> - Consider rate limiting and resource constraints
> - Understand that **all associated risks are the responsibility of the developer**
>
> For guidance on implementing these tools safely, refer to:
> - [OpenAI Shell Tool Safety Guide](https://platform.openai.com/docs/guides/tools-shell)
> - [Anthropic Bash Tool Documentation](https://docs.anthropic.com/en/docs/agents-and-tools/computer-use#understand-anthropics-computer-use-limitations)
>
> **We do not intend to provide further support for these tools beyond the type abstractions defined here.**
