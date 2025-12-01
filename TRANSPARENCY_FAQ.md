# Responsible AI Transparency FAQs

**What is Microsoft Agent Framework?**

Microsoft Agent Framework is a comprehensive multi-language (C#/.NET and Python) framework for building, orchestrating, and deploying AI agents and multi-agent workflows. The system takes user instructions and conversation inputs and produces intelligent responses through AI agents that can integrate with various LLM providers (OpenAI, Azure OpenAI, Azure AI Foundry). It provides both simple chat agents and complex multi-agent workflows with graph-based orchestration.

**What can Microsoft Agent Framework do?**

The framework offers: 

- **Agent Creation**: Build AI agents with custom instructions and tools
- **Multi-Agent Orchestration**: Group chat, sequential, concurrent, and handoff patterns
- **Graph-based Workflows**: Connect agents and deterministic functions using data flows with streaming, checkpointing, time-travel, and Human-in-the-loop
- **Extensibility Framework**: Extend with native functions, A2A, Model Context Protocol (MCP)
- **LLM Integration**: Support for OpenAI, Azure OpenAI, Azure AI Foundry, and other providers
- **Runtime Support**: Both in-process and distributed agent execution

**What is/are Microsoft Agent Framework's intended use(s)?**

Intended uses include: 

- **Enterprise AI Applications**: Building AI-powered business applications with multiple specialized agents
- **Multi-Agent Collaboration**: Coordinating multiple AI agents for complex tasks (e.g., content creation with writer/reviewer agents)
- **Workflow Automation**: Orchestrating AI agents and deterministic functions in business processes

**How was Microsoft Agent Framework evaluated? What metrics are used to measure performance?**

Microsoft Agent Framework is a development framework rather than a deployed AI system. The framework undergoes engineering testing for component functionality, integration testing for multi-agent scenarios, and conformance testing across .NET and Python implementations. However, AI performance metrics such as accuracy, helpfulness, and safety are dependent on the underlying LLM providers and specific application implementations. Developers using the framework should conduct application-specific evaluation including performance, safety, and accuracy testing appropriate to their chosen LLM providers, deployment contexts, and use cases.

**What are the limitations of Microsoft Agent Framework? How can users minimize the impact of Microsoft Agent Framework's limitations when using the system?**

Microsoft Agent Framework relies on existing LLMs. Using the framework retains common limitations of large language models, including:

**LLM-Inherited Limitations**:

- **Data Biases**: Large language models, trained on extensive data, can inadvertently carry biases present in the source data. Consequently, the models may generate outputs that could be potentially biased or unfair.
- **Lack of Contextual Understanding**: Despite their impressive capabilities in language understanding and generation, these models exhibit limited real-world understanding, resulting in potential inaccuracies or nonsensical responses.
- **Lack of Transparency**: Due to the complexity and size, large language models can act as 'black boxes,' making it difficult to comprehend the rationale behind specific outputs or decisions.
- **Content Harms**: There are various types of content harms that large language models can cause. It is important to be aware of them when using these models, and to take actions to prevent them. It is recommended to leverage various content moderation services provided by different companies and institutions.
- **Inaccurate or ungrounded content**: It is important to be aware and cautious not to entirely rely on a given language model for critical decisions or information that might have deep impact as it is not obvious how to prevent these models to fabricate content without high authority input sources.
- **Potential for Misuse**: Without suitable safeguards, there is a risk that these models could be maliciously used for generating disinformation or harmful content.

**Framework-Specific Limitations**:

- **Platform Requirements**: Python 3.10+ required, specific .NET versions (.NET 8.0, 9.0, 10.0, netstandard2.0, net472)
- **API Dependencies**: Requires proper configuration of LLM provider keys and endpoints
- **Orchestration Features**: Advanced orchestration patterns including GroupChat, Sequential, and Concurrent workflows are now available in both Python and .NET implementations. See the respective language documentation for examples.
- **Privacy and Data Protection**: The framework allows for human participation in conversations between agents. It is important to ensure that user data and conversations are protected and that developers use appropriate measures to safeguard privacy.
- **Accountability and Transparency**: The framework involves multiple agents conversing and collaborating, it is important to establish clear accountability and transparency mechanisms. Users should be able to understand and trace the decision-making process of the agents involved in order to ensure accountability and address any potential issues or biases.
- **Security & unintended consequences**: The use of multi-agent conversations and automation in complex tasks may have unintended consequences. Especially, allowing agents to make changes in external environments through tool calls or function execution could pose significant risks. Developers should carefully consider the potential risks and ensure that appropriate safeguards are in place to prevent harm or negative outcomes, including keeping a human in the loop for decision making.

**Mitigation Steps**:

- Follow setup guides for proper API key configuration
- Use provided samples as starting points to avoid configuration issues
- Monitor the GitHub repository for feature releases and updates
- Implement content moderation and safety measures when deploying agents
- Maintain human oversight for critical decisions and actions
- Use appropriate security measures to protect user data and conversations

**What operational factors and settings allow for effective and responsible use of Microsoft Agent Framework?**

**Configuration Requirements**:

- **API Keys**: Proper configuration of your LLM provider credentials and endpoints 

- **Model Selection**: Choose appropriate deployment models for specific use cases 

- **Tool Integration**: Careful selection and validation of external tools and MCP servers 

- **Type Safety**: Strong typing and compatibility validation between agents and threads 

 

**Responsible Development Practices**: 

- **Human Oversight**: Microsoft Agent Framework prioritizes human involvement in multi-agent conversations. Users should maintain oversight and can step in to provide feedback to agents and steer them in the correct direction. In critical applications, users should confirm actions before they are executed. 

- **Agent Modularity**: Modularity allows agents to have different levels of information access. Additional agents can assume roles that help keep other agents in check. For example, one can easily add a dedicated agent to play the role of safeguard. 

- **LLM Selection**: Users can choose the LLM that is optimized for responsible use. We encourage developers to review and follow LLM providers’ policies. Developers should add content moderation and/or use safety metaprompts when using agents, like they would do when using LLMs directly. 

- **Security Measures**: Implement appropriate security measures for tool execution and external system integrations. Consider using containerization or sandboxing for code execution scenarios to prevent unintended system changes. 

- **Testing and Validation**: Use provided testing frameworks (unit, integration, conformance tests) to validate agent behavior and ensure reliability. 

- **Monitoring and Observability**: Implement proper error handling, logging, and use OpenTelemetry for observability to track agent behavior and identify potential issues. 

 

**How do I provide feedback on Microsoft Agent Framework?**

- **Bug Reports**: File issues at https://github.com/microsoft/agent-framework/issues

**What are external services and how does Microsoft Agent Framework use them?**

The framework supports multiple external service types: 

- **Native Functions**: Custom Python/C# functions that agents can invoke
- **A2A (Agent2Agent)Integration**: Agent-to-agent communication and coordination
- **Model Context Protocol (MCP)**: External tools and data sources through MCP servers
- **Tools & External Capabilities**: Agent-invokable external services

External service development is open to developers who can create custom functions and integrate external APIs. Users have control over which tools are provided to agents during agent creation.

**What data can Microsoft Agent Framework provide to external services? What permissions do Microsoft Agent Framework external services have?**

Microsoft Agent Framework is an open-source framework that allows integration with various types of external services. The data access and permissions depend on how you configure and implement these integrations:

**Data Access by Service Type**:

- **Native Functions**: Custom functions you develop have access to whatever data you explicitly pass to them as parameters
- **A2A (Agent2Agent)**: External agents can access conversation history, messages, and any data you configure to share through the communication interface
- **Model Context Protocol (MCP) Servers**: External MCP servers can access data according to the specific MCP server implementation and your configuration
- **External Tools**: Third-party tools and APIs have access to data you explicitly send to them through function calls

**Important Security Considerations**:

- **Community and Third-Party Services**: Microsoft Agent Framework is an open-source project. When using community-developed tools or services from third-party providers, it is your responsibility to evaluate and ensure their safety, security, and compliance with your data protection requirements.
- **Data Boundary Considerations**: When connecting Azure-hosted agents to external agents or services, data may leave the Azure boundary and Microsoft's security perimeter. You should verify the data handling practices, security measures, and compliance certifications of external providers before sharing sensitive or regulated data.
- **Provider Due Diligence**: Before integrating any external service, you should review their privacy policies, security practices, data retention policies, and terms of service to ensure they meet your organization's requirements and regulatory obligations.
- **Data Minimization**: Only provide external services with the minimum data necessary for their function. Avoid sharing sensitive, personal, or confidential information unless absolutely required and properly secured.

**Recommendation**: Consult with your organization's security, privacy, and legal teams before integrating external services, especially in production environments handling sensitive data.

**What kinds of issues may arise when using Microsoft Agent Framework enabled with external services?**

**Potential Issues**:

- **API Key Security**: Risk of exposing API keys in configuration or logs
- **Tool Reliability**: External tool failures or unavailability affecting agent performance
- **Type Safety**: Mismatched message types between agents and handlers
- **Provider Dependencies**: Reliance on external LLM provider availability and rate limits

**Mitigation Mechanisms**:

- Follow security best practices for API key management
- Implement proper error handling for tool failures
- Use strong typing and compatibility validation
- Monitor external service health and implement fallback strategies
- Regular repository updates during preview period for bug fixes 
