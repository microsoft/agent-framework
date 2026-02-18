# Human-in-Loop Workflow Sample

This sample demonstrates how to build interactive workflows that request user input during execution using the `Question`, `RequestExternalInput`, and `WaitForInput` actions.

## What This Sample Shows

- Using `Question` to prompt for user responses
- Using `RequestExternalInput` to request external data
- Using `WaitForInput` to pause and wait for input
- Processing user responses to drive workflow decisions
- Interactive conversation patterns

## Files

- `workflow.yaml` - The declarative workflow definition
- `main.py` - Python script that loads and runs the workflow with simulated user interaction

## Running the Sample

1. Ensure you have the package installed:
   ```bash
   cd python
   pip install -e packages/agent-framework-declarative
   ```

2. Run the sample:
   ```bash
   python main.py
   ```

## How It Works

The workflow demonstrates a simple survey/questionnaire pattern:

1. **Greeting**: Sends a welcome message
2. **Question 1**: Asks for the user's name
3. **Question 2**: Asks how they're feeling today
4. **Processing**: Stores responses and provides personalized feedback
5. **Summary**: Summarizes the collected information

The `main.py` script shows how to handle `ExternalInputRequest` to provide responses during workflow execution.

## Key Concepts

### ExternalInputRequest

When a human-in-loop action is executed, the workflow yields an `ExternalInputRequest` containing:
- `variable`: The variable path where the response should be stored
- `prompt`: The question or prompt text for the user

The workflow runner should:
1. Detect `ExternalInputRequest` in the event stream
2. Display the prompt to the user
3. Collect the response
4. Resume the workflow (in a real implementation, using external loop patterns)

### ExternalLoopEvent

For more complex scenarios where external processing is needed, the workflow can yield an `ExternalLoopEvent` that signals the runner to pause and wait for external input.
