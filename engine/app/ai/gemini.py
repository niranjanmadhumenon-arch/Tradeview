"""Thin Gemini client: one generateContent call over HTTPS, text in, text out.
No tools, no code execution, no function calling are enabled."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.8-flash"


class InsightError(RuntimeError):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def generate(api_key: str, model: str, system_instruction: str, payload: dict, timeout: float = 60) -> str:
    body = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(payload, indent=1)}]}],
        "generationConfig": {"maxOutputTokens": 4096},
    }
    request = urllib.request.Request(
        ENDPOINT.format(model=model),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as res:
            data = json.loads(res.read())
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        if exc.code in (400, 401, 403) and "key" in detail.lower():
            raise InsightError("Gemini rejected the API key. Check it and save it again.", 401) from exc
        if exc.code == 404:
            raise InsightError(f"Gemini model '{model}' was not found. Set QT_GEMINI_MODEL to a current model.") from exc
        if exc.code == 429:
            raise InsightError("Gemini rate limit or quota reached. Try again shortly.", 429) from exc
        raise InsightError(f"Gemini request failed (HTTP {exc.code}). {detail}".strip()) from exc
    except urllib.error.URLError as exc:
        raise InsightError("Could not reach Gemini. Check the internet connection.") from exc

    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "no response")
        raise InsightError(f"Gemini returned no memo ({reason}).")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        raise InsightError(f"Gemini returned an empty memo ({candidates[0].get('finishReason', 'unknown')}).")
    return text
