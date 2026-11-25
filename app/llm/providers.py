"""
LLM providers: the "brains" the gateway can talk to.

Every provider has the same shape, so the gateway can swap them freely:

    provider.generate(messages, max_tokens, timeout) -> LLMResult

messages = [{"role": "system" | "user" | "assistant", "content": "..."}]

Providers here:
  - GeminiProvider : Google Gemini in the cloud (needs GEMINI_API_KEY)
  - OllamaProvider : a model running on this computer via Ollama (no key, free)
"""

from dataclasses import dataclass

import httpx


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class ProviderError(Exception):
    """
    Something went wrong talking to a provider.
    retryable=True  -> worth trying again (timeout, rate limit 429, server error 5xx, no connection)
    retryable=False -> trying again won't help (bad key 401/403, bad request 400)
    """

    def __init__(self, message, retryable):
        super().__init__(message)
        self.retryable = retryable


def _raise_for_status(response, provider_name):
    if response.status_code < 400:
        return
    retryable = response.status_code == 429 or response.status_code >= 500
    # Add the provider's own short explanation (e.g. "model not found") to help debugging.
    # Never include headers or the request URL: they can contain the API key.
    detail = ""
    try:
        err = response.json().get("error", "")
        detail = (err.get("message", "") if isinstance(err, dict) else str(err))[:200]
    except ValueError:
        pass
    message = f"{provider_name} returned HTTP {response.status_code}" + (f": {detail}" if detail else "")
    raise ProviderError(message, retryable=retryable)


class GeminiProvider:
    name = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key, model):
        self.api_key = api_key
        self.model = model

    def generate(self, messages, max_tokens=512, timeout=20.0):
        # Gemini wants the system prompt separately, and calls the assistant "model"
        system = " ".join(m["content"] for m in messages if m["role"] == "system")
        contents = [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages if m["role"] != "system"
        ]
        body = {"contents": contents, "generationConfig": {"maxOutputTokens": max_tokens}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        try:
            response = httpx.post(
                f"{self.BASE_URL}/{self.model}:generateContent",
                headers={"x-goog-api-key": self.api_key},   # key in a header, never in the URL
                json=body,
                timeout=timeout,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ProviderError(f"gemini connection problem: {type(exc).__name__}", retryable=True)
        _raise_for_status(response, self.name)

        data = response.json()
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            raise ProviderError("gemini returned no answer (possibly blocked)", retryable=False)
        usage = data.get("usageMetadata", {})
        return LLMResult(text=text, provider=self.name, model=self.model,
                         input_tokens=usage.get("promptTokenCount", 0),
                         output_tokens=usage.get("candidatesTokenCount", 0))


class OllamaProvider:
    name = "ollama"

    def __init__(self, model, base_url="http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def generate(self, messages, max_tokens=512, timeout=60.0):
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False,
                      "options": {"num_predict": max_tokens}},
                timeout=timeout,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ProviderError(f"ollama connection problem: {type(exc).__name__}", retryable=True)
        _raise_for_status(response, self.name)

        data = response.json()
        return LLMResult(text=data.get("message", {}).get("content", ""), provider=self.name,
                         model=self.model, input_tokens=data.get("prompt_eval_count", 0),
                         output_tokens=data.get("eval_count", 0))
