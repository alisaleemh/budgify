import json
import os
import urllib.request
from dataclasses import dataclass
from typing import List, Protocol

from transaction_tracker.core.models import Transaction

from huggingface_hub import InferenceClient

_OLLAMA_URL = "http://localhost:11434/api/chat"


_OPENAI_URL = "https://api.openai.com/v1/chat/completions"


class LLMProvider(Protocol):
    def generate(self, messages: List[dict]) -> str:
        """Return a completion for the given chat messages."""


@dataclass
class HuggingFaceProvider:
    model: str
    token: str | None = None

    def __post_init__(self) -> None:
        self._client = InferenceClient(provider="cerebras", api_key=self.token)

    def generate(self, messages: List[dict]) -> str:
        out = self._client.chat_completion(messages=messages, model=self.model)
        return out.choices[0].message.content.strip()


@dataclass
class OpenAIProvider:
    model: str
    api_key: str

    def generate(self, messages: List[dict]) -> str:
        payload = {"model": self.model, "messages": messages}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(_OPENAI_URL, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(req) as resp:
            resp_data = json.load(resp)
        return resp_data["choices"][0]["message"]["content"].strip()


@dataclass
class OllamaProvider:
    model: str
    url: str = _OLLAMA_URL

    def generate(self, messages: List[dict]) -> str:
        payload = {"model": self.model, "messages": messages, "stream": False}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(self.url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req) as resp:
            resp_data = json.load(resp)
        return resp_data.get("message", {}).get("content", "").strip()


def _tx_to_line(tx: Transaction) -> str:
    return f"{tx.date.isoformat()} | {tx.description} | {tx.merchant} | {tx.amount:.2f}"


def get_provider_from_env() -> LLMProvider:
    provider = os.environ.get("BUDGIFY_LLM_PROVIDER", "huggingface").lower()
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        model = os.environ.get("BUDGIFY_LLM_MODEL", "gpt-3.5-turbo")
        return OpenAIProvider(model=model, api_key=api_key)
    if provider == "ollama":
        model = os.environ.get("BUDGIFY_LLM_MODEL", "llama3")
        url = os.environ.get("OLLAMA_URL", _OLLAMA_URL)
        return OllamaProvider(model=model, url=url)
    token = os.environ.get("HF_API_TOKEN")
    model = os.environ.get("BUDGIFY_LLM_MODEL", "Qwen/Qwen3-32B")
    return HuggingFaceProvider(model=model, token=token)


def generate_report(transactions: List[Transaction], provider: LLMProvider | None = None) -> str:
    """Send transactions to an LLM and return a textual report."""
    if not transactions:
        return "No transactions to analyze."

    provider = provider or get_provider_from_env()
    lines = [_tx_to_line(tx) for tx in transactions]
    messages = [
        {"role": "system", "content": 
            "Provide a short financial summary and insights for the user based on these transactions."},
        {"role": "user", "content": "\n".join(lines)},
    ]
    try:
        return provider.generate(messages)
    except Exception as e:
        return f"Error contacting LLM: {e}"
