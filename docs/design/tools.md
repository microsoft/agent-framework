# Tools

The design goal is to make it easy to create new tools and integrate existing
APIs and make them available to agents.

## `Tool` base class

```python
@dataclass
class ToolResult:
    """The result of running a tool."""
    is_error: bool
    output: List[ImageContent | TextContent] # The content types are defined as part of the core data types.
    ... # Other fields, could be extended to include more for application-specific needs.

class Tool(ABC):
    """The base class for all tools in the framework."""

    @property
    def name(self) -> str:
        """The name of the tool, used to identify it in the system."""
        ...
    
    @property
    def description(self) -> str:
        """The description of the tool, used to provide information about its
        functionality.
        """
        ...

    @property
    def schema(self) -> ToolSchema:
        """The schema of the tool, which defines the JSON schema of the input
        arguments."""
        ...

    @property
    def strict(self) -> bool:
        """Whether the JSON schema is in strict mode. If true, no optional
        arguments are allowed.
        """
        ...
    
    async def __call__(
        self,
        call: ToolCall,
        context: Context,
    ) -> ToolResult:
        """The method to call to run the tool with arguments and return the result.
        
        Args:
            call: The tool call containing the name and arguments to pass to the tool.
            context: The context for the current invocation of the tool, providing
                access to the event channel, and human-in-the-loop (HITL) features.

        Returns:
            The result of running the tool.
        """
        try:
            # Call the on_invoke method to allow for input guardrails to be applied
            # to the arguments before the tool is run.
            await self.on_invoke(args, context)
            # Call the run method to actually run the tool.
            result = await self.run(args, context)
            # Call the on_output method to handle the output of the tool.
            result = await self.on_output(result, context)
        except Exception as e:
            # If an error occurs, call the on_error method to handle it.
            result = await self.on_error(e, context)
        return result

    @abstractmethod
    async def run(
        self,
        calls: ToolCall,
        context: Context,
    ) -> ToolResult:
        """The method called by the tool itself to run the tool with arguments and return the result."""
        ...
    
    async def on_invoke(
        self,
        calls: ToolCall,
        context: Context,
    ) -> None:
        """The method called by the tool when is invoked but before it is run.

        This is useful for input guardrails to be applied to the arguments
        before the tool is run.
        """ 
        ...
    
    async def on_error(
        self,
        error: Exception,
        context: Context,
    ) -> ToolResult:
        """The method called by the tool when an error is raised."""
        ...
    
    async def on_output(
        self,
        output: ToolResult,
        context: Context,
    ) -> ToolResult:
        """The method called by the tool when the output is ready.

        This is where output guardrails can be applied to the result
        before it is returned to the caller.
        """
        ...
    
    def add_input_guardrails(
        self, 
        guardrails: list[InputGuardrail[ToolCall]]
    ) -> None:
        """Add input guardrails to the tool.

        Args:
            guardrails: The list of input guardrails to add.
        """
        ...
    
    def add_output_guardrails(
        self, 
        guardrails: list[OutputGuardrail[ToolResult]]
    ) -> None:
        """Add output guardrails to the tool.

        Args:
            guardrails: The list of output guardrails to add.
        """
        ...
    
    def add_on_error_func(
        self, 
        on_error_func: Callable[[Exception, Context], Awaitable[ToolResult]]
    ) -> None:
        """Add a function to call when an error is raised during the call to `run`.

        Args:
            on_error_func: The function to call when an error is raised.
        """
        ...
```

## `FunctionTool`

The `FunctionTool` is a decorator that can be used to create a tool from a function.

```python
@FunctionTool
def web_search(
    query: str,
    num_results: int = 10,
) -> str:
    """A tool that performs a web search and returns the results."""
    ...
```

`FunctionTool` supports customization of the following:
- `name`
- `description`
- `on_error_func`: the function to call when an error is raised during the call to `run`.
- `strict`: whether the JSON schema is in strict mode. If true, no optional
  arguments are allowed.
- `input_guardrails`: a list of input guardrails to apply to the arguments
  before the tool is run.
- `output_guardrails`: a list of output guardrails to apply to the result
  before it is returned.

## `AgentTool`

The `AgentTool` is a wrapper around an agent that can be used as a tool.

```python
agent = SomeAgent(...)
tool = AgentTool(
    agent=agent,
    name="SomeAgent",
    description="Some description of this agent tool.",
    output_extractor=..., # Optional, a function to extract a ToolResult from the agent's run Result.
    on_error_func=..., # Optional, a function to call when an error is raised during the call to `run`.
)
```

The argument to the `AgentTool` is a single string.

> NOTE: Do we also need to support passing a thread to the agent tool?