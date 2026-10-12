"""Model adapters. Only Ollama is implemented; any object with `.generate(messages)` and `.describe()` works."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_HOST = "http://localhost:11434"


@dataclass
class Generation:
    text: str | None
    latency_s: float
    error: str | None = None


class OllamaAdapter:
    """Calls a local Ollama server (/api/chat, non-streaming). Uses only the standard library."""

    def __init__(self, model: str, host: str = DEFAULT_HOST, temperature: float = 0.0,
                 seed: int = 0, timeout: float = 300.0):
        self.model, self.host, self.timeout = model, host.rstrip("/"), timeout
        self.options = {"temperature": temperature, "seed": seed}

    def describe(self) -> dict:
        return {"provider": "ollama", "name": self.model, "host": self.host, "options": self.options}

    def generate(self, messages: list[dict]) -> Generation:
        body = json.dumps({"model": self.model, "messages": messages, "stream": False,
                           "options": self.options}).encode()
        req = urllib.request.Request(f"{self.host}/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
            text = data["message"]["content"]
            return Generation(text, time.perf_counter() - start)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            hint = f" (is the model pulled? try: ollama pull {self.model})" if e.code == 404 else ""
            return Generation(None, time.perf_counter() - start, f"HTTP {e.code}: {detail}{hint}")
        except urllib.error.URLError as e:
            return Generation(None, time.perf_counter() - start,
                              f"Cannot reach Ollama at {self.host} ({e.reason}). Is `ollama serve` running?")
        except (KeyError, json.JSONDecodeError, TimeoutError, OSError) as e:
            return Generation(None, time.perf_counter() - start, f"{type(e).__name__}: {e}")
