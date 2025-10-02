---
# These are optional elements. Feel free to remove any of them.
status: Proposed
contact: eavanvalkenburg
date: 2025-09-17
deciders: markwallace-microsoft, dmytrostruk, ekzhu, sphenry, giles17
consulted: taochenosu, alliscode, moonbox3, johanste, stephentoub
---

# Additional types - types and tools

## Context and Problem Statement

There are a number of capabilities that are available for chat clients that either lack a content types to accurately capture the response, or that lack a abstracted tool to allow interchangeability between chat clients. This ADR captures the proposed new types and tools, the rationale, and the alternatives considered and rejected.

Currently in MEAI there are: HostedCodeInterpreterTool, HostedFileSearchTool, HostedMcpServerTool, HostedWebSearchTool.

For each of these, there are two decisions, the first is whether or not we need something new for it, and the second is what to call it, to make it easy these are grouped into the same considered options section. The `do nothing` option is always listed last, this is not a indication of preference either way, just a way to make it easy to see what the options are.

## Decision Drivers

- Consistent naming with current types and tools.
- Interoperability between chat clients.
- Ease of implementation and adoption.

# Tools

## Image generation tools

Multiple API's currently support Image Generation tools, such as OpenAI Responses [here](https://platform.openai.com/docs/api-reference/responses/create#responses-create-tools). And [Mistral](https://docs.mistral.ai/agents/connectors/image_generation/), For OpenAI and Mistral this can be enabled by adding: `{"type": "image_generation"}` to the tools list. You then get image data back in the response, inputs can be both text and images. Google so far, has only created specific models that can be prompted to return a generated image, no tool specified.

### Considered Options

1. HostedImageGenerationTool
    - Pro: easier to use then a dict, can be extended later, and the additional_properties can be used to allow additional parameters, if those become needed.
    - Con: only available in limited number of API's currently.
1. Nothing, allow the dict to be passed and show samples of how this works.
    - Pro: No extra effort needed.
    - Con: less discoverable, no type checking.

### Decision Outcome

1. HostedImageGenerationTool - include a HostedImageGenerationTool that can be used like this:

```python
tools = [
    get_weather,
    HostedCodeInterpreterTool(),
    HostedImageGenerationTool()
]
```
Without additional parameters for now, Mistral AI does not take any additional parameters, while OpenAI has a bunch, which can be put into additional_properties for now.
We can add uniform parameters later, if needed.

## Computer Use Tools

Multiple API's currently support Computer Use tools, such as OpenAI Responses [here](https://platform.openai.com/docs/guides/tools-computer-use). Claude does this as well [here](https://docs.claude.com/en/docs/agents-and-tools/tool-use/computer-use-tool)

Setup for OpenAI:
```json
{
    "type": "computer_use_preview",
    "display_width": 1024,
    "display_height": 768,
    "environment": "browser" # other possible values: "mac", "windows", "ubuntu"
}
```

Setup for claude:
```json
{
    "type": "computer_20250124",
    "name": "computer",
    "display_width_px": 1024,
    "display_height_px": 768,
    "display_number": 1,
}
```

The model then returns a call to make and it might need screenshots to be taken and sent.

Support for this would entail providing a out of the box local setup for the computer to use, or good samples showing how this can be setup with playwright or docker for OpenAI and a local sandbox for Claude.

### Considered Options

1. ComputerUseTool
    - Pro: easier to use then a dict, can be extended later, and the additional_properties can be used to allow additional parameters, if those become needed.
    - Con: only available in limited number of API's currently and expectation would likely be to also include a local setup for it, which will be difficult to unify across platforms and providers. Would also require a additional Content Type
2. Nothing, allow the dict to be passed and show samples of how this works.
    - Pro: No extra effort needed.
    - Con: less discoverable, no type checking.

### Decision Outcome

2. Nothing, allow the dict to be passed and for the moment we will not add samples as the receiving side of a computer use setup is quite complex, and depends on the local system, software and other factors. We will monitor usage and if this becomes more popular we can add a ComputerUseTool later.


## Bash or Shell Tools

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
    "type": "local_shell"
}
```

The commands should then be taken and executed with the local shell session. In OpenAI Agents SDK this is built in, with something called the `LocalShellExecutor`.

The bash and computer use tools are often used in conjunction to allow more control over a local machine.

### Considered Options

1. BashTool
    - Pro: easier to use then a dict, can be extended later, and the additional_properties can be used to allow additional parameters, if those become needed.
    - Con: only available in limited number of API's currently and expectation would likely be to also include a local setup for it, which will be difficult to unify across platforms and providers. Would also require a additional Content Type
    - Alternative names: ShellTool, LocalShellTool, LocalBashTool
2. Nothing, allow the dict to be passed and show samples of how this works.
    - Pro: No extra effort needed.
    - Con: less discoverable, no type checking.

### Decision Outcome

2. Nothing, allow the dict to be passed and for the moment we will not add samples as the receiving side of a bash tool setup is quite complex, and depends on the local system, software and other factors. We will monitor usage and if this becomes more popular we can add a BashTool later.

# Tools meta alternative

Currently in Python we allow you to pass a dict to the tools parameter which allows for all of these tools to be passed in, we could consider a generic `HostedTool` (or some other name) class that you instantiate with the dict for that api and that would be passed through. This makes them feel a bit more like first class citizens, it is still not a fully abstracted tool, but might be a good middle ground.

### Current:
```python
tools = [
    get_weather,
    HostedCodeInterpreterTool(),
    {"type": "image_generation"},
    {"type": "computer_use_preview", "environment": "browser", "display_width": 1024, "display_height": 768},
    {"type": "local_shell"}
]
```
### Meta tool approach
```python
tools = [
    get_weather,
    HostedCodeInterpreterTool(),
    HostedTool(type="image_generation"),
    HostedTool(type="computer_use_preview", environment="browser", display_width=1024, display_height=768),
    HostedTool(type="local_shell")
]
```

## Options

1. HostedTool class
    - Pro: looks cleaner then a dict, would only supply `type` as a parameter, and even that might break for some API's.
    - Con: only marginally easier to use then a dict, and does not provide any additional type safety or discoverability. Not a full abstraction of the tools, so not a lot of added value.
    - Alternative names: GenericHostedTool, GenericTool
2. HostedTool typeddict with total=False
    - Pro: looks cleaner then a dict, would only supply `type` as a parameter, and even that might break for some API's. Would make usage optional compared to a class.
    - Con: only marginally easier to use then a dict, and does not provide any additional type safety or discoverability. Not a full abstraction of the tools, so not a lot of added value.
    - Alternative names: GenericHostedTool, GenericTool
3. Nothing, allow the dict to be passed and show samples of how this works.

## Decision

3. Nothing, allow the dict to be passed and for the moment we will not add samples as the receiving side of a bash tool setup is quite complex, and depends on the local system, software and other factors. We will monitor usage and if this becomes more popular we can add a HostedTool later.

# Types

Several of the specialized tools also return specialized response types that are not currently modeled in MEAI. Adding these types would allow for better type checking and intellisense.

## Code interpreter response type

The Code Interpreter tool returns a response that is often comprised of code, other inputs, stdout logs and files (usually images, for instance plots).

The interesting thing about the code interpreter is that it can play the role both of a tool that get's executed to provide the right context or as a way to generate the response. In the first case you could consider the inputs and outputs as Annotation or a form of Reasoning, while in the latter it makes more sense to consider it a Content.

### Considered Options

1. As new content type
    - Pro: fits well with the current model of chat responses being comprised of content.
    - Con: might be confusing as it is not a single content type, but a combination of multiple.
    - names: CodeInterpreterContent, CodeExecutionResultContent, CodeExecutionContent or CodeContent
        - Fields: inputs, outputs, or code, logs, files (potentially list of DataContent)
1. As existing content types (TextContent, DataContent)
    - Pro: no new types needed.
    - Con: less discoverable, no type checking, TextContent is handled different from others by `text` property on responses (to mitigate we could use TextReasoningContent instead of TextContent). More difficult to show the inputs and outputs together as they might be split into Text and Data contents.
    - names: reuse existing types TextContent and DataContent
1. As Annotation
    - Pro: fits with the notion of the code being used to add additional context to the response.
    - Con: less discoverable compared to Content and not always consistent with how the tool is used.
    - names: CodeInterpreterAnnotation or CodeAnnotation

### Decision Outcome

1. As new content type - `CodeExecutionContent` with fields:
    - This name is chosen because it is more generic than CodeInterpreterContent, as it could be used for other code execution tools in the future.
    - Further, it is shorter than CodeExecutionResultContent, which is a bit long and since there might be no result of a code execution, it is better to not include Result in the name.
    - This also means this can be used to supply code (set `inputs` only) to a service in the future, not just code that is generated and executed automatically.
    - Fields:
        - inputs and outputs, both of type `list[Contents]`.
            - DataContent is used for files, with appropriate mime-types.
            - DataContent is used for code being run, with mime-type `text/x-python` or similar for other programming languages.
            - TextContent is used for logs and stdout.
            - ErrorContent is used for stderr or similar error output.
        - `text` property that is a concatenation of all `TextContent` in the `outputs` field.
