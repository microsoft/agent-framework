# MCP Servers

An MCP server is a component that wraps a session to an
[Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server.

The tools provided by MCP server should match the tool interface to ensure
minimal boilerplate code when dealing with both tools and MCP servers.

Other features like sampling and resources, should be accessible through
the MCP server interface as well.


## MCP Server base class (draft)

```python

class MCPServer(ABC):
    """The base class for all MCP servers in the framework."""

    @abstractmethod
    async def list_tools(self, context: Context) -> list[ToolSchema]:
        """List all available tools in the MCP server.

        Returns:
            A list of tool schemas available in the MCP server.
        """
        ...

    @abstractmethod
    async def call_tool(
        self,
        call: ToolCall,
        context: Context,
    ) -> ToolResult:
        """Call a tool with the given name and arguments.

        Args:
            tool_name: The name of the tool to call.
            args: The arguments to pass to the tool.
            context: The context for the current invocation of the MCP server.

        Returns:
            The result of calling the tool.
        """
        ...
    
    def add_input_guardrails(
        self, 
        guardrails: list[InputGuardrail[ToolCall]]
    ) -> None:
        """Add input guardrails to the MCP server.

        Args:
            guardrails: The list of input guardrails to add.
        """
        ...
    
    def add_output_guardrails(
        self, 
        guardrails: list[OutputGuardrail[ToolResult]]
    ) -> None:
        """Add output guardrails to the MCP server.

        Args:
            guardrails: The list of output guardrails to add.
        """
        ...
    
```

MCP specs have other APIs. We should consider adding them as well.