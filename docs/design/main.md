# Agent Framework Design Doc (Draft)

## Core Concepts

### Component

A component is a class that provides a specific functionality and can be used
independently by applications.

Components can be composed to create complex components.
It is the responsibility of the framework to validate components
and their composition.

_Question: should components be serializable?_

### Model Client

A model client is a component that implements a unified interface for
interacting with different language models. It exposes a standardized metadata
about the model it provides (e.g., model name, tool call and vision capabilities, etc.)
to support validation and composition with other components.

### Model Context

Model context (or simply "context") refers to data types that are produced by
or consumed by language models. For example, Chat Completion messages,
text, images, audio, etc.

### Model Context Provider

A model context provider is an abstract component that provides context to
language models and can be invoked using on data in the context.

### Tool

A tool is a model context provider that can be used to invoke procedure code
and returns the result as context to the language model.
Tool can have arguments for invocation. 
The arguments must be defined using JSON schema that language model supports.

### Workbench

A workbench is a model context provider that provides a set of tools sharing
a common state or resource. 

_Question: should a tool be a workbench?_

### Memory

A memory is a model context provider that stores arbitrary data types while providing
an interface for retrieving context from the stored data for language models.

Some memory implementations may also provides tools or workbench
for storing and retreiving context.

### Thread

A thread is a model context provider that stores the message history
used with a chat-based language model.


### Agent

An agent is a component that takes an input data type and produces a stream
of output data types.

A typical agent is a complex component consisting of a model client,
a tool or a workbench, a memory and a state.


## Opinions

### The purpose of an agent framework

An agent framework should first and foremost provide the components for building agents and workflows.
For each component, the framework should provide clear value proposition on why it should be used.