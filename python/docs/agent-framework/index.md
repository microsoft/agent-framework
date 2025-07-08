---
myst:
  html_meta:
    "description lang=en": |
      Top-level documentation for Agent Framework, a framework for developing applications using AI agents
html_theme.sidebar_secondary.remove: false
sd_hide_title: true
---

<style>
.hero-title {
  font-size: 60px;
  font-weight: bold;
  margin: 2rem auto 0;
}

.wip-card {
  border: 1px solid var(--pst-color-success);
  background-color: var(--pst-color-success-bg);
  border-radius: .25rem;
  padding: 0.3rem;
  display: flex;
  justify-content: center;
  align-items: center;
  margin-bottom: 1rem;
}
</style>

# Agent Framework

<div class="container">
<div class="row text-center">
<div class="col-sm-12">
<h1 class="hero-title">
Agent Framework
</h1>
<h3>
A framework for building AI agents and applications
</h3>
</div>
</div>
</div>

<div style="margin-top: 2rem;">

::::{grid}
:gutter: 2

:::{grid-item-card} {fas}`cube;pst-color-primary` Agent Framework [![PyPi agent-framework](https://img.shields.io/badge/PyPi-agent--framework-blue?logo=pypi)](https://pypi.org/project/agent-framework/)
:shadow: none
:margin: 2 0 0 0
:columns: 12 12 12 12

Create and manage AI agents, workflows, and applications using the Agent Framework. It provides:

* Deterministic and dynamic agentic workflows for business processes.
* Research on multi-agent collaboration.
* Distributed agents for multi-language applications.

_Start here if you are getting serious about building multi-agent systems._

+++

```{button-ref} reference/index
:color: secondary

Get Started
```

:::

:::{grid-item-card} {fas}`puzzle-piece;pst-color-primary` Extensions [![PyPi agent-framework](https://img.shields.io/badge/PyPi-autogen--ext-blue?logo=pypi)](https://pypi.org/search/?q=agent-framework-)
:shadow: none
:margin: 2 0 0 0
:columns: 12 12 12 12

Implementations of connectors and other external components for the Agent Framework. These extensions allow you to connect to various AI models, services, and tools, enhancing the capabilities of your agents.

* {py:class}`~agent-framework-openai` for using OpenAI models.
* {py:class}`~agent-framework-azure` for using Azure services.
+++

:::

::::

</div>

```{toctree}
:maxdepth: 3
:hidden:

reference/index
```
