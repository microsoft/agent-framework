# Microsoft Agent Framework Workflows Core Concepts: Edges

This document provides an in-depth look at the **Edges** component of the Microsoft Agent Framework Workflow system.

## Overview

Edges define how messages flow between executors with optional conditions. They represent the connections in the workflow graph and determine the data flow paths.

### Types of Edges

The framework supports several edge patterns:

1. **Direct Edges**: Simple one-to-one connections between executors
2. **Conditional Edges**: Edges with conditions that determine when messages should flow
3. **Fan-out Edges**: One executor sending messages to multiple targets
4. **Fan-in Edges**: Multiple executors sending messages to a single target

#### Direct Edges

The simplest form of connection between two executors:



Coming soon...


#### Conditional Edges

Edges that only activate when certain conditions are met:



Coming soon...


#### Fan-out Edges

Distribute messages from one executor to multiple targets:



Coming soon...


#### Fan-in Edges

Collect messages from multiple sources into a single target:



Coming soon...


## Next Step

- [Learn about Workflows](../workflows.md) to understand how to build and execute workflows.
