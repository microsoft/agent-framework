---
status: accepted
contact: eavanvalkenburg
date: 2025-09-19
deciders: eavanvalkenburg, markwallace-microsoft,  ekzhu, sphenry, alliscode
consulted: taochenosu, moonbox3, dmytrostruk, giles17
---

# Python Subpackages Design

## Context and Problem Statement

The goal is to design a subpackage structure for the Python agent framework that balances ease of use, maintainability, and scalability. How can we organize the codebase to facilitate the development and integration of connectors while minimizing complexity for users?

## Decision Drivers

- Ease of use for developers
- Maintainability of the codebase
- User experience for installing and using the integrations
- Clear lifecycle management for integrations
- Minimize non-GA dependencies in the main package

## Considered Options

1. One subpackage per vendor, so a `google` package that contains all Google related connectors, such as `GoogleChatClient`, `BigQueryCollection`, etc.
    * Pros:
        - fewer packages to manage, publish and maintain
        - easier for users to find and install the right package.
        - users that work primarily with one platform have a single package to install.
    * Cons:
        - larger packages with more dependencies
        - larger installation sizes
        - more difficult to version, since some parts may be GA, while other are in preview.
2. One subpackage per connector, so a i.e. `google_chat` package, a i.e. `google_bigquery` package, etc.
    * Pros:
        - smaller packages with fewer dependencies
        - smaller installation sizes
        - easy to version and do lifecycle management on
    * Cons:
        - more packages to manage, register, publish and maintain
        - more extras, means more difficult for users to find and install the right package.
3. Group connectors by vendor and maturity, so that you can graduate something from the i.e. the `google-preview` package to the `google` package when it becomes GA.
    * Pros:
        - fewer packages to manage, publish and maintain
        - easier for users to find and install the right package.
        - users that work primarily with one platform have a single package to install.
        - clear what the status is based on extra name
    * Cons:
        - moving something from one to the other might be a breaking change
        - still larger packages with more dependencies
    It could be mitigated that the `google-preview` package is still imported from `agent_framework.google`, so that the import path does not change, when something graduates, but it is still a clear choice for users to make. And we could then have three extras on that package, `google`, `google-preview` and `google-all` to make it easy to install the right package or just all.
4. Group connectors by vendor and type, so that you have a `google-chat` package, a `google-data` package, etc.
    * Pros:
        - smaller packages with fewer dependencies
        - smaller installation sizes
    * Cons:
        - more packages to manage, register, publish and maintain
        - more extras, means more difficult for users to find and install the right package.
        - still keeps the lifecycle more difficult, since some parts may be GA, while other are in preview.
5. Add `meta`-extras, that combine different subpackages as one extra, so we could have a `google` extra that includes `google-chat`, `google-bigquery`, etc.
    * Pros:
        - easier for users on a single platform
    * Cons:
        - more packages to manage, register, publish and maintain
        - more extras, means more difficult for users to find and install the right package.
        - makes developer package management more complex, because that meta-extra will include both GA and non-GA packages, so during dev they could use that, but then during prod they have to figure out which one they actually need and make a change in their dependencies, leading to mismatches between dev and prod.
6. Make all imports happen from `agent_framework.connectors` (or from two or three groups `agent_framework.chat_clients`, `agent_framework.context_providers`, or something similar) while the underlying code comes from different packages.
    * Pros:
        - best developer experience, since all imports are from the same place and it is easy to find what you need, and we can raise a meaningfull error with which extra to install.
        - easier for users to find and install the right package.
    * Cons:
        - larger overhead in maintaining the `__init__.py` files that do the lazy loading and error handling.
        - larger overhead in package management, since we have to ensure that the main package.
7. Subpackage existence will be based off status of dependencies and/or possibilities of a external support mechanism. What this means is that:
    - Integrations that need non-GA dependencies will be subpackages, so that we can avoid having non-GA dependencies in the main package.
    - Integrations where the AF-code is still experimental, preview or release candidate will be subpackages, so that we can avoid having non-GA code in the main package and we can version those packages properly.
    - Integrations that are outside Microsoft and where we might not always be able to fast-follow breaking changes, will stay as subpackages, to provide some isolation and to be able to version them properly.
    - Integrations that are mature and that have released (GA) dependencies and or features on the service side will be moved into the main package, the dependencies of those packages will stay installable under the same `extra` name, so that users do not have to change anything, and we then remove the subpackage itself.
    - All subpackage imports in the code should be from a stable place, mostly vendor-based, so that when something moves from a subpackage to the main package, the import path does not change, so `from agent_framework.google import GoogleChatClient` will always work, even if it moves from the `agent-framework-google` package to the main `agent-framework` package.
    - The imports in those vendor namespaces (these won't be actual python namespaces, just the folders with a __init__.py file and any code) will do lazy loading and raise a meaningful error if the subpackage or dependencies are not installed, so that users know which extra to install with ease.
    - On a case by case basis we can decide to create additional `extras`, that combine multiple subpackages into one extra, so that users that work primarily with one platform can install everything they need with a single extra, for instance you can install with the `agent-framework[azure-purview]` extra that only implement a Azure Purview Middleware, or you can install with the `agent-framework[azure]` extra that includes all Azure related connectors, like `purview`, `content safety` and others (all examples, not actual packages (yet)), regardless of where the code sits, these should always be importable from `agent_framework.azure`.
    - Subpackage naming should also follow this, so in principle a package name is `<vendor/folder>-<feature/brand>`, so `google-gemini`, `azure-purview`, `microsoft-copilotstudio`, etc. For smaller vendors, with less likely to have a multitude of connectors, we can skip the feature/brand part, so `mem0`, `redis`, etc.

## Decision Outcome

Option 7: This provides us a good balance between developer experience, user experience, package management and maintenance, while also allowing us to evolve the package structure over time as dependencies and features mature. And it ensures the main package, installed without extras does not include non-GA dependencies or code, extras do not carry that guarantee, for both the code and the dependencies.

# Microsoft vs Azure packages
Another consideration is for Microsoft, since we have a lot of Azure services, but also other Microsoft services, such as Microsoft Copilot Studio, and potentially other services in the future, and maybe Foundry also will be marketed separate from Azure at some point. We could also have both a `microsoft` and an `azure` package, where the `microsoft` package contains all Microsoft services, excluding Azure, while the `azure` package only contains Azure services. Only applicable for the variants where we group by vendor, including with meta packages.

## Decision Outcome
Azure and Microsoft will be the two vendor folders for Microsoft services, so Copilot Studio will be imported from `agent_framework.microsoft`, while Foundry, Azure OpenAI and other Azure services will be imported from `agent_framework.azure`.
