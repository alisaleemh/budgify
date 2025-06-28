import json
import os
import urllib.request
import logging
from dataclasses import dataclass
from typing import List, Protocol

from transaction_tracker.core.models import Transaction
from huggingface_hub import InferenceClient
from abc import ABC, abstractmethod

# -----------------------------------------------------------------------------
# Configure basic debug logging (caller can override)

# -----------------------------------------------------------------------------
logging.basicConfig(level=os.getenv("LLM_DEBUG", "INFO").upper())
logger = logging.getLogger(__name__)

_OLLAMA_URL = "http://localhost:11434/api/chat"
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"


class LLMProvider(Protocol):
    """A minimal protocol all concrete providers must implement."""

    def generate(self, messages: List[dict]) -> str:  # noqa: D401 – keep simple signature
        """Return the model reply given a list-of-dicts chat history."""


# -----------------------------------------------------------------------------
# Hugging Face Inference API provider (unchanged)
# -----------------------------------------------------------------------------

@dataclass
class LLMClient:
    """Simple client that delegates chat requests to an LLM provider."""
    provider: LLMProvider | None = None

    def __post_init__(self) -> None:
        if self.provider is None:
            self.provider = get_provider_from_env()

    def chat(self, messages: List[dict]) -> str:
        return self.provider.generate(messages)


@dataclass
class HuggingFaceProvider:
    model: str
    token: str | None = None

    def __post_init__(self) -> None:
        self._client = InferenceClient(provider="cerebras", api_key=self.token)

    def generate(self, messages: List[dict]) -> str:
        out = self._client.chat_completion(messages=messages, model=self.model)
        return out.choices[0].message.content.strip()


# -----------------------------------------------------------------------------
# OpenAI Chat Completions provider (unchanged)
# -----------------------------------------------------------------------------

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


class BaseAIOutput(ABC):
    """Composable layer for building prompts and parsing LLM responses."""

    @abstractmethod
    def build_messages(self, transactions: List[Transaction]) -> List[dict]:
        """Return chat messages describing the task."""

    def post_process(self, response: str) -> str:
        return response

    def generate(self, transactions: List[Transaction], client: LLMClient | None = None) -> str:
        if not transactions:
            return "No transactions to analyze."
        client = client or LLMClient()
        messages = self.build_messages(transactions)
        try:
            out = client.chat(messages)
        except Exception as e:
            return f"Error contacting LLM: {e}"
        return self.post_process(out)


class InsightsReport(BaseAIOutput):
    """Default report describing transaction insights."""

    def build_messages(self, transactions: List[Transaction]) -> List[dict]:
        lines = [_tx_to_line(tx) for tx in transactions]
        return [
            {
                "role": "system",
                "content": "Provide a short financial summary and insights for the user based on these transactions.",
            },
            {"role": "user", "content": "\n".join(lines)},
        ]
# -----------------------------------------------------------------------------
# Ollama provider with robust parsing and debug logging
# -----------------------------------------------------------------------------

@dataclass
class OllamaProvider:
    model: str
    url: str = _OLLAMA_URL

    def _post(self, payload: dict) -> dict:
        """Low‑level helper: POST JSON and return parsed JSON with debug logs."""
        data = json.dumps(payload).encode()
        logger.debug("Ollama ▶ POST %s – payload: %s", self.url, payload)
        req = urllib.request.Request(self.url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            logger.debug("Ollama ◀ %s", raw)
            return json.loads(raw)

    def generate(self, messages: List[dict]) -> str:
        payload = {"model": self.model, "messages": messages, "stream": False}
        resp_data = self._post(payload)

        # Ollama /api/chat returns either {'message': str, 'done': bool}
        # or {'message': {'role': 'assistant', 'content': str, ...}, 'done': bool}
        msg = resp_data.get("message", "")
        if isinstance(msg, dict):
            msg = msg.get("content", "")
        if not isinstance(msg, str):
            raise RuntimeError(f"Unexpected Ollama response format: {resp_data}")
        return msg.strip()


# -----------------------------------------------------------------------------
# Helper utilities
# -----------------------------------------------------------------------------

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
        model = os.environ.get("BUDGIFY_LLM_MODEL", "phi3:mini")
        url = os.environ.get("OLLAMA_URL", _OLLAMA_URL)
        return OllamaProvider(model=model, url=url)

    # Default → Hugging Face
    token = os.environ.get("HF_API_TOKEN")
    model = os.environ.get("BUDGIFY_LLM_MODEL", "Qwen/Qwen3-32B")
    return HuggingFaceProvider(model=model, token=token)


# -----------------------------------------------------------------------------
# Public helper – generate a textual insights report
# -----------------------------------------------------------------------------

def generate_report(transactions: List[Transaction], provider: LLMProvider | None = None) -> str:
    """Convenience wrapper returning an insights report."""
    client = LLMClient(provider)
    report = InsightsReport()
    return report.generate(transactions, client)
