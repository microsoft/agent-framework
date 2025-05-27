# Core Data Types

To unify the interaction between components, we define a set of core
data types that are used throughout the framework.

For example, text, images, function calls, tool schema are
all examples of such data types.
These data types are used to interact with agent components (model clients, tools, MCP, threads, and memory),
forming the connective tissue between those components.

In AutoGen, these are the data types mostly defined in `autogen_core.models` module,
and others like `autogen_core.Image` and `autogen_core.FunctionCall`. This is just
an example as AutoGen has no formal definition of model context.

A design goal of the new framework to simplify the interaction between agent components
through a common set of data types, minimizing boilerplate code
in the application for transforming data between components.

To start, we should follow the MEAI standard.