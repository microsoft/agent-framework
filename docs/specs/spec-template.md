---
# These are optional elements. Feel free to remove any of them.
status: {proposed | rejected | accepted | deprecated | … | superseded by [SPEC-0001](0001-spec.md)}
contact: {person proposing the ADR}
date: {YYYY-MM-DD when the decision was last updated}
deciders: {list everyone involved in the decision}
consulted: {list everyone whose opinions are sought (typically subject-matter experts); and with whom there is a two-way communication}
informed: {list everyone who is kept up-to-date on progress; and with whom there is a one-way communication}
---

# {short title of solved problem and solution}

## What is the goal of this feature?

Make sure to cover:
1. What is the value we are providing to users
1. Include one success metric
1. Implementation free description of outcome

Consult PM on this.

For example:

We want users to be able to refer to external Azure resources easily when consuming them in other features like indexes, agents,
and evaluations. We know we're successful when 40% of project client users are using connections.

## What is the problem being solved?

Make sure to cover:
1. Why is this hard today?
1. Customer pain points?
1. Reducing system complexity (maintenance costs, latency, etc)?

Consult PM on this.

For example:

Today, users have to understand control plane vs data plane endpoints and use multiple packages to stitch their application
code together. This makes using our product confusing and also increases the number of dependencies a customer will have
in their code.

## API Changes

List all new API changes

## E2E Code Samples

Include python or C# examples of how you expect this feature to be used with other things in our system.

For example:

This connection name is unique across the resource. Given a resource name, system should be able to unambiguously resolve a
connection name. A connection name can be used to pass along connection details to individual features. Services will be able to parse this ID and use it to access the underlying resource. The below example shows how a connection can be used to create a dataset.

```python
client.datasets.create_dataset(
    name="evaluation_dataset",
    file="myblob/product1.pdf",
    connection = "my-azure-blob-connection"
)
```

How to use a connection when creating an `AzureAISearchIndex`

```python
from azure.ai.projects.models import AzureAISearchIndex

azure_ai_search_index = AzureAISearchIndex(
    name="azure-search-index",
    connection="my-ai-search-connection",
    index_name="my-index-in-azure-search",
)

created_index = client.indexes.create_index(azure_ai_search_index)
```
