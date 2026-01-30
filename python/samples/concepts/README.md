# Concept Samples

This folder contains samples that dive deep into specific Agent Framework concepts.

## Samples

| Sample | Description |
|--------|-------------|
| [response_stream.py](response_stream.py) | Deep dive into `ResponseStream` - the streaming abstraction for AI responses. Covers the four hook types (transform hooks, cleanup hooks, finalizer, result hooks), two consumption patterns (iteration vs direct finalization), and the `wrap()` API for layering streams without double-consumption. |
| [typed_options.py](typed_options.py) | Demonstrates TypedDict-based chat options for type-safe configuration with IDE autocomplete support. |
