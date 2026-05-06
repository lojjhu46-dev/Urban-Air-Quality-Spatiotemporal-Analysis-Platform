from __future__ import annotations

import pytest
import requests

from src.deepseek_client import (
    coerce_tool_arguments,
    deepseek_chat_completion,
    deepseek_http_error,
    deepseek_json_completion,
    deepseek_model_candidates,
    extract_json_object,
)


def test_deepseek_model_candidates_adds_compat_model_for_flash_alias() -> None:
    assert deepseek_model_candidates("deepseek-v4-flash") == ["deepseek-v4-flash", "deepseek-chat"]
    assert deepseek_model_candidates("deepseek-chat") == ["deepseek-chat"]


def test_extract_json_object_accepts_plain_and_fenced_content() -> None:
    assert extract_json_object('prefix {"city": "Berlin"} suffix') == {"city": "Berlin"}
    assert extract_json_object('```json\n{"city": "Tokyo"}\n```') == {"city": "Tokyo"}


def test_extract_json_object_rejects_missing_object() -> None:
    with pytest.raises(ValueError, match="JSON object not found"):
        extract_json_object("not json")


def test_coerce_tool_arguments_accepts_dict_json_string_and_fenced_json() -> None:
    assert coerce_tool_arguments({"city": "Berlin"}) == {"city": "Berlin"}
    assert coerce_tool_arguments('{"city": "Berlin"}') == {"city": "Berlin"}
    assert coerce_tool_arguments('```json\n{"city": "Tokyo"}\n```') == {"city": "Tokyo"}
    assert coerce_tool_arguments("") == {}


def test_deepseek_http_error_includes_model_and_response_detail() -> None:
    class FakeResponse:
        text = ""

        def json(self) -> dict[str, object]:
            return {"error": {"message": "tool calls unavailable"}}

    wrapped = deepseek_http_error(
        FakeResponse(),  # type: ignore[arg-type]
        requests.HTTPError("400 Client Error"),
        "deepseek-v4-flash",
    )

    assert "400 Client Error" in str(wrapped)
    assert "Model: deepseek-v4-flash" in str(wrapped)
    assert "tool calls unavailable" in str(wrapped)


def test_deepseek_chat_completion_retries_with_compat_model() -> None:
    attempted_models: list[str] = []

    class FakeResponse:
        def __init__(self, status_code: int, body: dict[str, object]) -> None:
            self.status_code = status_code
            self._body = body
            self.text = ""

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code} Client Error")

        def json(self) -> dict[str, object]:
            return self._body

    def fake_post(url: str, headers: dict[str, str], json: dict[str, object], timeout: int):
        del url, headers, timeout
        attempted_models.append(str(json["model"]))
        assert json.get("thinking") == {"type": "disabled"}
        if json["model"] == "deepseek-v4-flash":
            return FakeResponse(400, {"error": {"message": "model alias unavailable"}})
        return FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})

    payload = deepseek_chat_completion(
        [{"role": "user", "content": "test"}],
        api_key="sk-test",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        thinking_type="disabled",
        post=fake_post,
    )

    assert attempted_models == ["deepseek-v4-flash", "deepseek-chat"]
    assert payload["choices"][0]["message"]["content"] == "ok"


def test_deepseek_json_completion_returns_parsed_content() -> None:
    def fake_chat_completion(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        return {"choices": [{"message": {"content": '```json\n{"city": "Berlin"}\n```'}}]}

    payload = deepseek_json_completion(
        [{"role": "user", "content": "test"}],
        api_key="sk-test",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        chat_completion=fake_chat_completion,
    )

    assert payload == {"city": "Berlin"}
