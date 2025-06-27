from transaction_tracker.ai import LLMClient, InsightsReport
from transaction_tracker.core.models import Transaction
from datetime import date

class DummyProvider:
    def __init__(self):
        self.messages = []
    def generate(self, messages):
        self.messages.append(messages)
        return "ok"

def test_insights_report_with_client():
    tx = Transaction(date=date(2025, 5, 1), description="desc", merchant="m", amount=1.0)
    client = LLMClient(provider=DummyProvider())
    report = InsightsReport().generate([tx], client)
    assert report == "ok"
