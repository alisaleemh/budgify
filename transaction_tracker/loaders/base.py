# transaction_tracker/loaders/base.py
from abc import ABC, abstractmethod

class BaseLoader(ABC):
    @abstractmethod
    def load(self, file_path):
        """
        Yield Transaction instances from file_path.
        """
        pass