from .base import EvalBase

class AgentEvaluation(EvalBase):
    def evaluate(self, agent, test_cases):
        report = []
        for case in test_cases:
            try:
                output = agent.run(case["input"])
                passed = output == case["expected_output"]
                report.append({"input": case["input"], "expected": case["expected_output"], "output": output, "passed": passed})
            except Exception as e:
                report.append({"input": case["input"], "error": str(e), "passed": False})
        return report
