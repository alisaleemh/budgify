# transaction_tracker/outputs/base.py
from abc import ABC, abstractmethod

class BaseOutput(ABC):
    @abstractmethod
    def append(self, transactions, month=None):
        """Append transactions to the chosen sink."""
        pass