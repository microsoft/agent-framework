from .base import EvalBase

class GenAIEval(EvalBase):
    def evaluate(self, agent, prompts):
        results = []
        for prompt in prompts:
            response = agent.run(prompt)
            results.append({"input": prompt, "output": response, "length": len(response)})
        return results
