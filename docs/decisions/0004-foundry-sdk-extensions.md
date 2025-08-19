---
# These are optional elements. Feel free to remove any of them.
status: proposed
contact: markwallace-microsoft
date: 2025-08-06
deciders: markwallace-microsoft, westey-m, quibitron, trrwilson
consulted: 
informed: 
---

# `Azure.AI.Agents.Persistent` package Extensions Methods for Agent Framework

## Context and Problem Statement

To align the `Azure.AI.Agents.Persistent` package and Agent Framework a set of extensions methods have been created which allow a developer to create or retrieve an `AIAgent` using the `PersistentAgentsClient`.
The purpose of this ADR is to decide where these extension methods should live.

## Decision Drivers

- Provide the optimum experience for developers.
- Avoid adding additional dependencies to the `Azure.AI.Agents.Persistent` package (and not in the future)

## Considered Options

- Add the extension methods to the `Azure.AI.Agents.Persistent` package and change it's dependencies
- Add the extension methods to the `Azure.AI.Agents.Persistent` package without changing it's dependencies
- Add the extension methods to a `Microsoft.Extensions.AI.Azure` package


### Add the extension methods to the `Azure.AI.Agents.Persistent` package and change it's dependencies

- `Azure.AI.Agents.Persistent` would depend on `Microsoft.Extensions.AI` instead of `Microsoft.Extensions.AI.Abstractions`

- Good because, extension methods are in the `Azure.AI.Agents.Persistent` package and can be easily kept up-to-date
- Good because, developers don't need to explicitly depend on a new package to get Agent Framework functionality
- Bad because, it introduces additional dependencies which would possibly grow overtime


### - Add the extension methods to the `Azure.AI.Agents.Persistent` package without changing it's dependencies

- `Azure.AI.Agents.Persistent` would depend on `Microsoft.Extensions.AI.Abstractions` (as it currently does)
- `ChatClientAgent` and `FunctionInvokingChatClient` would move to `Microsoft.Extensions.AI.Abstractions`

- Good because, extension methods are in the `Azure.AI.Agents.Persistent` package and can be easily kept up-to-date
- Good because, developers don't need to explicitly depend on a new package to get Agent Framework functionality
- Good because, it introduces minimal additional dependencies
- Bad because, it adds additional dependencies to `Microsoft.Extensions.AI.Abstractions` and these additional dependencies add up as transitive to `Azure`.AI.Agents.Persistent`


### Add the extension methods to a `Microsoft.Extensions.AI.Azure` package

- Introduce a new package called `Microsoft.Extensions.AI.Azure` where the extension methods would live
- `Azure.AI.Agents.Persistent` does not change

- Good because, it introduces no additional dependencies to `Azure.AI.Agents.Persistent` package
- Bad because, extension methods are not in the `Azure.AI.Agents.Persistent` package and cannot be easily kept up-to-date
- Bad because, developers need to explicitly depend on a new package to get Agent Framework functionality

## Decision Outcome

Chosen option: "Add the extension methods to a `Microsoft.Extensions.AI.Azure` package", because
it introduces no additional dependencies to `Azure.AI.Agents.Persistent` package.
