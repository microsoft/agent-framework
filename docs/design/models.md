# Model Clients

Model clients are used to interact with locally and remotely hosted language 
models.

The design goal is to provide integration with a wide range of model providers,
including both open-source and commercial models, while maintaining a consistent
interface for developers to use.

## `ModelClient` base class (draft)

```python
class ModelClient(ABC):
    """The base class for all model clients in the framework."""

    @abstractmethod
    async def create(
        self,
        messages: list[Message],
        context: Context,
        stream: bool = False,
        tools: Optional[list[Tool]] = None,
        output_format: Optional[OutputFormat] = None,
    ) -> Message:
        """Generate a response from the model based on the provided messages.

        Args:
            messages: The list of messages to process.
            context: The context for the current invocation of the model client.
                This is for accessing event channels for streaming tokens.
            stream: Whether to stream the response tokens.
            tools: Optional list of tools to use for tool calling.
            output_format: Optional structured output format for the response.
                If provided, the model will generate a response in this format
                and returns a structured response message.

        Returns:
            The generated response message.
        """
        ...
    
    def add_input_guardrails(
        self, 
        guardrails: list[InputGuardrail[Message]]
    ) -> None:
        """Add input guardrails to the model client.

        Args:
            guardrails: The list of input guardrails to add.
        """
        ...
    
    def add_output_guardrails(
        self, 
        guardrails: list[OutputGuardrail[Message]]
    ) -> None:
        """Add output guardrails to the model client.

        Args:
            guardrails: The list of output guardrails to add.
        """
        ...
```