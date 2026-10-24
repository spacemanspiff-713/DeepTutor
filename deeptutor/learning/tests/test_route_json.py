"""Tests for the resilient route-JSON helper.

Two failures motivated this module, and both are exercised here as the
regression they are:

* a reply that is valid JSON except for markdown emphasis inside a string
  (``\\*``), where a strict parse would discard an otherwise complete route,
  and
* a reasoning model returning no usable visible content, where the only useful
  behaviour is one retry on a dedicated route model — opt-in, because a retry
  bills the learner and may target another provider.
"""

import json

import pytest

from deeptutor.learning import route_json
from deeptutor.learning.route_json import (
    RouteJsonError,
    complete_route_json,
    escape_invalid_json_backslashes,
    parse_route_json,
    route_retry_enabled,
)


def _route(modules: int = 2) -> dict:
    return {
        "description": "A bounded route.",
        "modules": [
            {"name": f"Region {index}", "objective": f"Objective {index}"}
            for index in range(modules)
        ],
    }


class TestEscapeInvalidBackslashes:
    def test_repairs_markdown_emphasis(self):
        # ``\*`` is not a legal JSON escape; the payload is otherwise fine.
        assert escape_invalid_json_backslashes(r'{"a": "x \*able_id"}') == (
            r'{"a": "x \\*able_id"}'
        )

    def test_leaves_valid_escapes_alone(self):
        """The regression a naive lookahead caused: ``\\`` must survive intact."""
        original = r'{"a": "line\nnext\ttab\"quote\\slash\/forward"}'
        assert escape_invalid_json_backslashes(original) == original

    def test_escapes_a_stray_backslash_before_punctuation(self):
        # An escaped space is not a legal JSON escape and is common in
        # model-authored markdown.
        assert escape_invalid_json_backslashes('{"a": "x\\ y"}') == '{"a": "x\\\\ y"}'

    def test_escapes_a_backslash_at_the_end_of_the_payload(self):
        assert escape_invalid_json_backslashes('{"a": "x\\') == '{"a": "x\\\\'

    def test_repairs_an_incomplete_unicode_escape(self):
        # \u12 is not a valid \uXXXX escape, so the backslash is prose.
        assert escape_invalid_json_backslashes(r'{"a": "\u12"}') == r'{"a": "\\u12"}'


class TestParseRouteJson:
    def test_parses_strict_json(self):
        assert parse_route_json(json.dumps(_route())) == _route()

    def test_recovers_markdown_escapes_inside_json(self):
        """The exact shape that lost a complete model reply in the fork."""
        raw = '{"modules": [{"name": "Region", "objective": "Uses \\\\*able_id fields"}]}'
        parsed = parse_route_json(raw)
        assert parsed is not None
        assert parsed["modules"][0]["objective"] == r"Uses \*able_id fields"

    def test_strips_thinking_tags_before_parsing(self):
        raw = " thinkingconsidering the route…</think>" + json.dumps(_route())
        parsed = parse_route_json(raw, binding="openrouter", model="x-ai/grok-4.5")
        assert parsed == _route()

    def test_returns_none_for_empty_payload(self):
        assert parse_route_json("") is None
        assert parse_route_json("   \n  ") is None

    def test_returns_none_for_non_json_prose(self):
        assert parse_route_json("I could not produce a route, sorry.") is None

    def test_returns_none_for_non_object_json(self):
        assert parse_route_json("[1, 2, 3]") is None

    def test_required_key_rejects_parseable_but_wrong_structure(self):
        # Valid JSON, but not a route — as unusable as garbage, so it must not
        # be accepted just because it parsed.
        payload = json.dumps({"description": "no modules here"})
        assert parse_route_json(payload) is not None
        assert parse_route_json(payload, required_key="modules") is None

    def test_required_key_accepts_present_key(self):
        assert parse_route_json(json.dumps(_route()), required_key="modules") == _route()


class TestRouteRetryEnabled:
    def test_disabled_by_default(self, monkeypatch):
        """Retrying on another model is a cost decision, so it is opt-in."""
        monkeypatch.setattr(route_json, "ROUTE_MODEL", "")
        assert route_retry_enabled() is False

    def test_enabled_when_a_route_model_is_configured(self, monkeypatch):
        monkeypatch.setattr(route_json, "ROUTE_MODEL", "x-ai/grok-4.5")
        assert route_retry_enabled() is True


class TestCompleteRouteJson:
    @pytest.mark.asyncio
    async def test_uses_the_supplied_first_attempt_when_it_answers(self, monkeypatch):
        """``first_attempt`` is the caller's completion callable, so the call
        stays stubbable at its original import site."""
        calls: list[str] = []

        async def fake_complete(**kwargs):
            calls.append("configured")
            return json.dumps(_route())

        async def fail_if_called(**kwargs):  # pragma: no cover - asserted below
            calls.append("route")
            raise AssertionError("route model must not run when the first answer is good")

        monkeypatch.setattr(route_json, "ROUTE_MODEL", "x-ai/grok-4.5")
        monkeypatch.setattr(route_json, "_complete_with_route_model", fail_if_called)

        result = await complete_route_json(
            system_prompt="s", prompt="p", first_attempt=fake_complete
        )
        assert result == _route()
        assert calls == ["configured"]

    @pytest.mark.asyncio
    async def test_falls_back_to_route_model_on_unusable_reply(self, monkeypatch):
        calls: list[str] = []

        async def fake_complete(**kwargs):
            calls.append("configured")
            raise RuntimeError("API returned empty choices")

        async def fake_route(**kwargs):
            calls.append("route")
            return json.dumps(_route())

        monkeypatch.setattr(route_json, "ROUTE_MODEL", "x-ai/grok-4.5")
        monkeypatch.setattr(route_json, "_complete_with_route_model", fake_route)

        result = await complete_route_json(
            system_prompt="s", prompt="p", first_attempt=fake_complete
        )
        assert result == _route()
        assert calls == ["configured", "route"]

    @pytest.mark.asyncio
    async def test_falls_back_when_first_reply_is_valid_json_but_not_a_route(self, monkeypatch):
        """A parseable non-route must retry, not slip through."""
        calls: list[str] = []

        async def fake_complete(**kwargs):
            calls.append("configured")
            return json.dumps({"description": "no modules"})

        async def fake_route(**kwargs):
            calls.append("route")
            return json.dumps(_route())

        monkeypatch.setattr(route_json, "ROUTE_MODEL", "x-ai/grok-4.5")
        monkeypatch.setattr(route_json, "_complete_with_route_model", fake_route)

        result = await complete_route_json(
            system_prompt="s",
            prompt="p",
            required_key="modules",
            first_attempt=fake_complete,
        )
        assert result == _route()
        assert calls == ["configured", "route"]

    @pytest.mark.asyncio
    async def test_recovers_a_markdown_damaged_reply_without_a_retry(self, monkeypatch):
        """Parse repair alone fixes this, so no second model call is spent."""

        async def fake_complete(**kwargs):
            return '{"modules": [{"name": "R", "objective": "uses \\\\*glob"}]}'

        async def fail_if_called(**kwargs):  # pragma: no cover - asserted below
            raise AssertionError("a repairable payload must not trigger a retry")

        monkeypatch.setattr(route_json, "ROUTE_MODEL", "x-ai/grok-4.5")
        monkeypatch.setattr(route_json, "_complete_with_route_model", fail_if_called)

        result = await complete_route_json(
            system_prompt="s",
            prompt="p",
            required_key="modules",
            first_attempt=fake_complete,
        )
        assert result["modules"][0]["objective"] == r"uses \*glob"

    @pytest.mark.asyncio
    async def test_raises_when_every_attempt_fails(self, monkeypatch):
        async def fake_complete(**kwargs):
            raise RuntimeError("API returned empty choices")

        async def fake_route(**kwargs):
            return "still not json"

        monkeypatch.setattr(route_json, "ROUTE_MODEL", "x-ai/grok-4.5")
        monkeypatch.setattr(route_json, "_complete_with_route_model", fake_route)

        with pytest.raises(RouteJsonError) as excinfo:
            await complete_route_json(
                system_prompt="s",
                prompt="p",
                required_key="modules",
                first_attempt=fake_complete,
            )

        message = str(excinfo.value)
        # A failure has to stay diagnosable: both attempts and both reasons.
        assert "configured model" in message
        assert "empty choices" in message
        assert "unusable JSON" in message

    @pytest.mark.asyncio
    async def test_no_retry_when_route_model_disabled(self, monkeypatch):
        calls: list[str] = []

        async def fake_complete(**kwargs):
            calls.append("configured")
            return "garbage"

        async def fail_if_called(**kwargs):  # pragma: no cover - asserted below
            calls.append("route")
            raise AssertionError("retry must be disabled when no route model is set")

        monkeypatch.setattr(route_json, "ROUTE_MODEL", "")
        monkeypatch.setattr(route_json, "_complete_with_route_model", fail_if_called)

        with pytest.raises(RouteJsonError):
            await complete_route_json(system_prompt="s", prompt="p", first_attempt=fake_complete)
        assert calls == ["configured"]
