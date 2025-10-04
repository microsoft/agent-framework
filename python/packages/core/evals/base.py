from abc import ABC, abstractmethod

class EvalBase(ABC):
    @abstractmethod
    def evaluate(self, agent, data):
        pass
