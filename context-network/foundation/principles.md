# Microsoft Agent Framework - Development Principles

## Purpose
This document outlines the core development principles and standards that guide the Microsoft Agent Framework project.

## Classification
- **Domain:** Foundation
- **Stability:** Stable
- **Abstraction:** Conceptual
- **Confidence:** Established

## Core Principles

### 1. Multi-Language Parity
**Principle**: Both Python and .NET implementations should provide equivalent functionality with language-appropriate idioms.

**Application**:
- Feature parity across languages
- Language-specific APIs that feel natural
- Shared conceptual models with different implementations
- Cross-language learning (patterns work in both)

### 2. Developer Experience First
**Principle**: APIs should be intuitive, discoverable, and hard to misuse.

**Application**:
- Clear, descriptive names
- Type hints and strong typing
- Comprehensive documentation
- Rich samples and examples
- Helpful error messages

### 3. Production-Ready by Default
**Principle**: Framework should support production use cases out of the box.

**Application**:
- Observability and telemetry built-in
- Error handling and retry logic
- Security considerations (authentication, authorization)
- Performance optimization
- Resource cleanup and lifecycle management

### 4. Extensibility Without Modification
**Principle**: Users should be able to extend functionality without modifying framework code.

**Application**:
- Plugin architectures
- Protocol-based abstractions
- Middleware patterns
- Custom provider support
- Hook and callback mechanisms

### 5. Explicit Over Implicit
**Principle**: Make behavior clear and predictable; avoid magic.

**Application**:
- Clear configuration
- Documented relationships
- Explicit navigation paths
- Transparent execution models
- No hidden side effects

## Code Quality Standards

### Python Standards

#### Formatting & Style
- **Tool**: Ruff formatter
- **Line Length**: 120 characters
- **Target**: Python 3.10+
- **Docstrings**: Google-style required for all public APIs

#### Type Checking
- **Pyright**: Strict mode enabled
- **Mypy**: Strict settings
- **Coverage**: 80%+ type coverage target

#### Function Design
- **Positional Parameters**: Max 3 for fully expected parameters
- **Keyword Parameters**: For all other parameters
- **Avoid Import Requirements**: Provide string-based overrides where possible
- **Document kwargs**: With references or explanations

#### Docstring Example
```python
def create_agent(name: str, chat_client: ChatClientProtocol) -> Agent:
    """Create a new agent with the specified configuration.

    Args:
        name: The name of the agent.
        chat_client: The chat client to use for communication.

    Returns:
        A configured Agent instance.

    Raises:
        ValueError: If name is empty.
    """
```

#### Logging
- **Use centralized logging**: `from agent_framework import get_logger`
- **Never use**: `logging.getLogger(__name__)` directly
- **Logger instances**: `logger = get_logger('agent_framework.azure')`

#### Design Patterns
- **Prefer Attributes Over Inheritance**: Use data attributes, not subclasses
  ```python
  # ✅ Preferred
  ChatMessage(role="user", content="Hello")

  # ❌ Avoid
  UserMessage(content="Hello")
  ```

#### Async-First
- All I/O operations use `async def`
- Assume asynchronous unless explicitly sync
- Provide async context managers for resources

### .NET Standards

#### Conventions
- Follow [.NET coding conventions](https://learn.microsoft.com/dotnet/csharp/fundamentals/coding-style/coding-conventions)
- Use `dotnet format` for consistent formatting
- XML documentation comments for public APIs

#### Patterns
- Dependency injection for service configuration
- Builder patterns for fluent APIs
- Async/await for I/O operations
- IDisposable/IAsyncDisposable for resource management

## Testing Principles

### Test Coverage
- **Target**: High coverage for core functionality
- **Required**: Tests for all new features and bug fixes
- **Integration Tests**: Mark with appropriate decorators/attributes

### Python Testing
```python
# Mark integration tests
@pytest.mark.azure
@pytest.mark.openai
@skip_if_integration_tests_disabled
async def test_feature():
    ...
```

### .NET Testing
- Use xUnit framework
- Test projects mirror source structure
- Integration tests in separate test classes

### Test Quality
- **Clear Test Names**: Describe what is being tested
- **Arrange-Act-Assert**: Clear test structure
- **Isolated Tests**: No dependencies between tests
- **Fast Tests**: Unit tests should be fast
- **Reliable Tests**: No flaky tests

## Contribution Principles

### Before Starting Work
1. **File an issue** for non-trivial changes
2. **Discuss approach** with maintainers
3. **Get agreement** on direction
4. **Assign issue** to yourself

### Development Workflow
1. **Create branch** with descriptive name
2. **Write tests** alongside code
3. **Run quality checks** before committing
4. **Create focused PRs** (one feature/fix per PR)
5. **Respond to feedback** promptly

### DO
- Follow existing code style
- Include tests with new features
- Use pre-commit hooks (Python)
- Update documentation as needed
- Keep PRs focused and manageable

### DON'T
- Submit large PRs without discussion
- Alter licensing files
- Skip tests or quality checks
- Make breaking changes without approval
- Introduce new dependencies without discussion

## Documentation Principles

### Code Documentation
- **Public APIs**: Must have complete documentation
- **Complex Logic**: Include explanatory comments
- **Examples**: Provide usage examples in docstrings
- **Type Information**: Use type hints/annotations

### User Documentation
- **Getting Started**: Clear onboarding path
- **Samples**: Comprehensive, runnable examples
- **API Reference**: Generated from code documentation
- **Guides**: Step-by-step tutorials

### Context Network Documentation
- **Planning Documents**: Architecture, decisions, designs
- **Process Documents**: Development workflows, procedures
- **Decision Records**: ADRs for significant choices
- **Regular Updates**: Keep documentation current

## Performance Principles

### Optimization Guidelines
- **Measure First**: Profile before optimizing
- **Lazy Loading**: Don't load what you don't need
- **Async I/O**: Never block on I/O operations
- **Resource Pooling**: Reuse expensive resources
- **Caching**: Cache when appropriate

### Python-Specific
- **Lazy Imports**: Minimize import overhead
- **Generator Expressions**: For large sequences
- **Type Hints**: Help JIT optimization
- **Avoid Sync in Async**: Don't block the event loop

### .NET-Specific
- **ValueTask**: For frequently sync-completing operations
- **ArrayPool**: For temporary buffers
- **Span<T>**: For memory-efficient operations
- **Avoid Allocations**: In hot paths

## Security Principles

### Defense in Depth
- **Input Validation**: Validate all external input
- **Output Encoding**: Encode output appropriately
- **Authentication**: Support secure auth mechanisms
- **Authorization**: Implement proper access controls
- **Secrets Management**: Never hardcode secrets

### Responsible AI
- **Content Filtering**: Support guardrails
- **Transparency**: Clear about AI-generated content
- **Privacy**: Protect user data
- **Safety**: Implement safety mechanisms

## Relationship Network
- **Prerequisite Information**:
  - [Project Definition](project_definition.md)
- **Related Information**:
  - [Architecture Overview](architecture.md)
  - [Development Processes](../processes/development.md)
- **Dependent Information**:
  - [Contributing Guide](../processes/contributing.md)
  - [Testing Guide](../processes/testing.md)
- **Implementation Details**:
  - [Decision Records](../decisions/index.md)

## Navigation Guidance
- **Access Context**: When contributing code or reviewing contributions
- **Common Next Steps**:
  - Start contributing → [Development Processes](../processes/development.md)
  - Understand decisions → [Decision Records](../decisions/index.md)
  - Language-specific → [Python](../domains/python/index.md) or [.NET](../domains/dotnet/index.md)
- **Related Tasks**: Code reviews, feature implementation, quality assurance

## Metadata
- **Created:** 2025-10-11
- **Last Updated:** 2025-10-11
- **Updated By:** Context Network Setup

## Change History
- 2025-10-11: Initial document created during context network setup
