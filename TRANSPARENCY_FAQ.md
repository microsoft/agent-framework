 Steps**:

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
