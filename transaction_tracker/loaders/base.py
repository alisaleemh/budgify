# transaction_tracker/loaders/base.py
from abc import ABC, abstractmethod

class BaseLoader(ABC):
    @abstractmethod
    def load(self, file_path: str, include_payments: bool = False):
        """
        Yield Transaction instances from file_path.
        If include_payments is False, filter out payment transactions.
        """
        pass