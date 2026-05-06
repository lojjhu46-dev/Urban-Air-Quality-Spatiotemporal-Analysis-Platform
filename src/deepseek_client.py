from __future__ import annotations

import json
from typing import Any, Callable

import requests

RequestPost = Callable[..., requests.Response]
ChatCompletion = Callable[..., dict[str, Any]]
ModelCandidates = Callable[[str], list[str]]
HttpErrorFactory = Callable[[requests.Response, requests.HTTPError, str], requests.HTTPError]


def deepseek_model_candidates(model: str) -> list[str]:
    candidates = [model]
    if model == "deepseek-v4-flash":
        candidates.append("deepseek-chat")
    return candidates


def deepseek_http_error(response: requests.Response, exc: requests.HTTPError, model: str) -> requests.HTTPError:
    detail = ""
    try:
        body = response.json()
    except Exception:  # noqa: BLE001
        body = response.text.strip()
    if isinstance(body, dict):
        raw_error = body.get("error") or body.get("message") or body.get("reason") or body
        detail = raw_error if isinstance(raw_error, str) else json.dumps(raw_error, ensure_ascii=False)
    else:
        detail = str(body).strip()

    message = f"{exc}. Model: {model}"
    if detail:
        message = f"{message}. Response: {detail}"
    return requests.HTTPError(message, response=response)


def deepseek_chat_completion(
    messages: list[dict[str, Any]],
    *,
    api_key: str,
    model: str,
    base_url: str,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | None = None,
    temperature: float = 0.1,
    timeout: int = 90,
    thinking_type: str | None = None,
    post: RequestPost | None = None,
    model_candidates: ModelCandidates = deepseek_model_candidates,
    http_error_factory: HttpErrorFactory = deepseek_http_error,
) -> dict[str, Any]:
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    candidates = model_candidates(model)
    request_post = post or requests.post
    last_error: requests.HTTPError | None = None

    for idx, candidate_model in enumerate(candidates):
        payload: dict[str, Any] = {
            "model": candidate_model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
        }
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if thinking_type is not None:
            payload["thinking"] = {"type": thinking_type}

        response = request_post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            wrapped = http_error_factory(response, exc, candidate_model)
            last_error = wrapped
            is_last_candidate = idx == len(candidates) - 1
            if response.status_code == 400 and not is_last_candidate:
                continue
            raise wrapped from exc
        return response.json()

    if last_error is not None:
        raise last_error
    raise RuntimeError("DeepSeek request failed before a response was returned.")


def deepseek_json_completion(
    messages: list[dict[str, Any]],
    api_key: str,
    model: str,
    base_url: str,
    timeout: int = 90,
    chat_completion: ChatCompletion = deepseek_chat_completion,
) -> dict[str, Any] | None:
    payload = chat_completion(
        messages,
        api_key=api_key,
        model=model,
        base_url=base_url,
        temperature=0.1,
        timeout=timeout,
        thinking_type="disabled",
    )
    choices = payload.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if not content:
        return None
    try:
        return extract_json_object(str(content))
    except Exception:  # noqa: BLE001
        return None


def coerce_tool_arguments(raw_arguments: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments

    text = str(raw_arguments or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return extract_json_object(text)


def extract_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.replace("json", "", 1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("JSON object not found in model response.")
    return json.loads(stripped[start : end + 1])
