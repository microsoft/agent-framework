# Agent Framework Lab - Agent Framework x Agent Lightning

RL Module for Microsoft Agent Framework

## Installation

```bash
pip install agent-framework-lab-lightning
```

## Usage

```python
from agent_framework.lab.lightning import YourClass

# Your usage example here
instance = YourClass()
```

## Overview

Brief description of what this lab package provides and its main features.

## Features

- Feature 1: Description
- Feature 2: Description
- Feature 3: Description

## Examples

### Basic Usage

```python
from agent_framework.lab.lightning import YourClass

# Example usage
```

### Advanced Usage

```python
# More advanced examples
```

## Common Debugging Tips

### Ray Starting Issues

If you encounter issues connecting to Ray (see error messages like the following):

```
ERROR services.py:1357 -- Failed to start the dashboard , return code -5
ERROR services.py:1382 -- Error should be written to 'dashboard.log' or 'dashboard.err'. We are printing the last 20 lines for you. See 'https://docs.ray.io/en/master/ray-observability/user-guides/configure-logging.html#logging-directory-structure' to find where the log file is.
core_worker_process.cc:232: Failed to register worker to Raylet: IOError: Failed to read data from the socket: End of file worker_id=01000000ffffffffffffffffffffffffffffffffffffffffffffffff
```

Please try to restart the Ray cluster manually:

```bash
ray stop
env RAY_DEBUG=legacy HYDRA_FULL_ERROR=1 VLLM_USE_V1=1 ray start --head --dashboard-host=0.0.0.0
```

Please run the command above in the same directory where you will run the training script. Also, if you are to use W&B to track your training, or use a private model from HuggingFace, you need to set the `WANDB_API_KEY` or `HF_TOKEN` environment variable before running `ray start`.

### Debugging the Agent

A lot of issues in agent training is related to the agent itself. The agent must be made sure to be runnable before it's sent to training.

In samples, we provide a `debug` mode to help you debug the agent. You can run the following command to debug the agent. For example, in math agent:

```bash
python samples/train_math_agent.py --mode debug
```

## API Reference

Document your main classes and functions here.

## Contributing

This package is part of the Microsoft Agent Framework Lab. Please see the main repository for contribution guidelines.

## License

This project is licensed under the MIT License - see the LICENSE file for details.