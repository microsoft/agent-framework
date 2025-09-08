# Running Agent Framework Python Examples

This guide explains different ways to run the Agent Framework examples and how to properly configure environment variables for each approach.

## Different Approaches to Running Examples

There are several ways to run the examples, each requiring different environment variable configurations:

### 1. Running within IDE (VS Code with F5)

If you clone the repository and run examples within an IDE like VS Code using F5:

1. Clone the repository:
   ```bash
   git clone https://github.com/microsoft/agent-framework.git
   cd agent-framework/python
   ```

2. Configure environment variables in the `agent-framework/python` folder by creating a `.env` file (use [.env.example](../../python/.env.example) as example):
   ```
   FOUNDRY_PROJECT_ENDPOINT=your_project_endpoint
   FOUNDRY_MODEL_DEPLOYMENT_NAME=your_model_deployment_name
   ```

3. Open the project in VS Code, choose an example and press F5 to run it.

### 2. Running with Terminal Command

If you clone the repository and run samples with `python sample.py` terminal command:

1. Clone the repository and navigate to the specific sample folder:
   ```bash
   git clone https://github.com/microsoft/agent-framework.git
   cd agent-framework/python/samples/getting_started/agents/foundry
   ```

2. Configure environment variables in the sample folder by creating a `.env` file where the sample is located:
   ```
   FOUNDRY_PROJECT_ENDPOINT=your_project_endpoint
   FOUNDRY_MODEL_DEPLOYMENT_NAME=your_model_deployment_name
   ```

3. Run the sample:
   ```bash
   python sample.py
   ```

### 3. Copy-Paste Code in Local Project

If you copy and paste code samples into your own local project setup:

1. Install the required dependencies in your local environment:
   ```bash
   pip install agent-framework
   ```

2. Set up environment variables based on your local project configuration (e.g., `.env` file in your project root, system environment variables, or your preferred configuration method).

3. Make sure the environment variables are accessible from where your Python script runs.
