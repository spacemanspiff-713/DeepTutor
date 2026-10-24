"""Resilient structured JSON for learning route generation.

Asking a model for a JSON route fails for two distinct reasons, and only one of
them is worth a second model call:

* a model can put markdown-ish prose inside its JSON (``\\*``, ``\\_``) that is
  not valid JSON, so a strict parse throws away a payload that was otherwise
  complete. Repairing this costs nothing and is always worth doing.
* a reasoning model can spend its budget on hidden reasoning and return no
  usable visible content at all. The only fix is another attempt, so this is
  opt-in: a second call bills the learner and may target a different provider,
  which is not a decision to make on their behalf by default.

So :func:`parse_route_json` is always in effect, and
:func:`complete_route_json` retries on a dedicated route model only when
``DEEPTUTOR_ROUTE_MODEL`` is configured.

Nothing here invents a route. The caller keeps its own validation and its own
deterministic behaviour, so a genuine failure still surfaces as an error — the
same contract upstream already had, with fewer spurious failures.

Provenance: this logic was earned in the fork's Courses compiler, where the
configured chat model returned empty or malformed planning JSON often enough to
make course creation unreliable, and where ``parse_json_response`` was observed
to return ``{}`` for a payload that ``json.loads`` accepted.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Awaitable, Callable

from deeptutor.services.llm import (
    clean_thinking_tags,
    complete,
    get_llm_config,
    get_token_limit_kwargs,
)
from deeptutor.utils.json_parser import parse_json_response

logger = logging.getLogger(__name__)

#: Dedicated model for structured route replies. Empty by default: retrying on
#: another model is a cost and provider decision that must be opt-in.
ROUTE_MODEL = os.getenv("DEEPTUTOR_ROUTE_MODEL", "")
ROUTE_BINDING = os.getenv("DEEPTUTOR_ROUTE_BINDING", "openrouter")
#: Hidden reasoning starves the visible answer on long structured outputs, so
#: the route model is asked for as little of it as possible.
ROUTE_REASONING_EFFORT = os.getenv("DEEPTUTOR_ROUTE_REASONING_EFFORT", "low")

#: A module plan with several regions and objectives is a long reply; the
#: default is sized for the larger end of ``MAX_MODULE_LIMIT``.
DEFAULT_ROUTE_MAX_TOKENS = 7600

#: A backslash plus a valid JSON escape, or a backslash on its own. Matching the
#: escape as a *unit* matters: a lookahead that only inspects the following
#: character also matches the second backslash of a legitimate ``\\`` pair, and
#: would corrupt every payload that was already correct.
_ESCAPE_OR_STRAY = re.compile(r'\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})?')

#: Signature of the completion callable a caller may supply for the first try.
CompleteFn = Callable[..., Awaitable[str]]


class RouteJsonError(RuntimeError):
    """No attempt produced usable route JSON."""


def escape_invalid_json_backslashes(value: str) -> str:
    r"""Escape backslashes that JSON does not accept (e.g. markdown ``\*``).

    Models routinely write markdown emphasis inside JSON strings. The result
    parses as valid JSON once the stray backslash is escaped, so this recovers
    a payload rather than guessing at one. Valid escapes — including ``\\``
    itself — are copied through untouched.
    """

    def render(match: re.Match[str]) -> str:
        token = match.group(0)
        # Length 1 means the backslash began no valid escape, so it is prose.
        return token if len(token) > 1 else "\\\\"

    return _ESCAPE_OR_STRAY.sub(render, value)


def parse_route_json(
    raw: str,
    *,
    binding: str | None = None,
    model: str | None = None,
    required_key: str | None = None,
) -> dict[str, Any] | None:
    """Parse a model reply into a usable dict, or ``None`` if unusable.

    Strict parsing is attempted first. Only when that fails is the payload
    repaired and re-parsed, and finally handed to the project's permissive
    parser, so a normal reply is never reinterpreted.

    ``required_key`` additionally rejects a reply that parses but is not the
    structure asked for (e.g. valid JSON with no ``modules``), because that is
    just as unusable as unparseable text and deserves the same retry.
    """
    text = str(raw or "")
    if not text.strip():
        return None
    cleaned = (
        clean_thinking_tags(text, binding, model).strip() if (binding or model) else text.strip()
    )

    for candidate in (cleaned, text.strip()):
        if not candidate:
            continue
        for value in (candidate, escape_invalid_json_backslashes(candidate)):
            if not value.strip():
                continue
            try:
                data = json.loads(value)
            except (json.JSONDecodeError, TypeError, ValueError):
                permissive = parse_json_response(value, fallback=None)
                data = permissive if isinstance(permissive, dict) else None
            if isinstance(data, dict) and data:
                if required_key is None or data.get(required_key):
                    return data
    return None


def route_retry_enabled() -> bool:
    """Whether a dedicated route model is configured for a second attempt."""
    return bool(ROUTE_MODEL.strip())


async def _complete_with_route_model(
    *,
    system_prompt: str,
    prompt: str,
    max_tokens: int,
) -> str:
    config = get_llm_config()
    base_url = os.getenv("DEEPTUTOR_ROUTE_BASE_URL") or config.base_url
    kwargs: dict[str, Any] = {
        "temperature": 0.25,
        "response_format": {"type": "json_object"},
        "reasoning_effort": ROUTE_REASONING_EFFORT,
    }
    kwargs.update(get_token_limit_kwargs(ROUTE_MODEL, max_tokens))
    return await complete(
        prompt=prompt,
        system_prompt=system_prompt,
        model=ROUTE_MODEL,
        api_key=config.api_key,
        base_url=base_url,
        api_version=getattr(config, "api_version", None),
        binding=ROUTE_BINDING,
        **kwargs,
    )


async def complete_route_json(
    *,
    system_prompt: str,
    prompt: str,
    max_tokens: int = DEFAULT_ROUTE_MAX_TOKENS,
    label: str = "route",
    required_key: str | None = None,
    first_attempt: CompleteFn | None = None,
) -> dict[str, Any]:
    """Return route JSON, repairing parse damage and optionally retrying.

    ``first_attempt`` lets the caller supply the completion callable for the
    first try, which keeps the call observable at its original import site (and
    therefore stubbable in tests) rather than hidden behind this module.

    Raises :class:`RouteJsonError` when no attempt produced usable JSON, with
    every attempt's reason attached — a failure must stay diagnosable rather
    than silently degrading.
    """
    attempts: list[tuple[str, str | None]] = [("configured model", None)]
    if route_retry_enabled():
        attempts.append((ROUTE_MODEL, ROUTE_MODEL))

    reasons: list[str] = []
    for attempt_model, model in attempts:
        try:
            if model is None:
                if first_attempt is not None:
                    raw = await first_attempt(prompt=prompt, system_prompt=system_prompt)
                else:
                    raw = await complete(prompt=prompt, system_prompt=system_prompt)
            else:
                raw = await _complete_with_route_model(
                    system_prompt=system_prompt,
                    prompt=prompt,
                    max_tokens=max_tokens,
                )
        except Exception as exc:  # provider/transport failure: try the next one
            reasons.append(f"{attempt_model}: {type(exc).__name__}: {exc}")
            logger.warning("Route JSON attempt via %s failed: %s", attempt_model, exc)
            continue

        data = parse_route_json(
            raw,
            binding=ROUTE_BINDING if model else None,
            model=model,
            required_key=required_key,
        )
        if data is not None:
            if model is not None:
                logger.info(
                    "Route JSON recovered by %s after the configured model failed",
                    model,
                )
            return data
        expected = f" (needs non-empty '{required_key}')" if required_key else ""
        reasons.append(f"{attempt_model}: unusable JSON{expected} ({len(str(raw or ''))} chars)")
        logger.warning("Route JSON attempt via %s returned unusable JSON", attempt_model)

    raise RouteJsonError(f"No attempt produced usable {label} JSON. " + "; ".join(reasons))


__all__ = [
    "DEFAULT_ROUTE_MAX_TOKENS",
    "ROUTE_BINDING",
    "ROUTE_MODEL",
    "ROUTE_REASONING_EFFORT",
    "RouteJsonError",
    "complete_route_json",
    "escape_invalid_json_backslashes",
    "parse_route_json",
    "route_retry_enabled",
]
