"""OpenRouter wrapper for Kimi K2.6 with hard budget enforcement.

Limits encoded in code, not policy:
- per-call: max 25K input tokens, max 4K output tokens
- per-ticket: $0.05 cumulative cap
- model: moonshotai/kimi-k2.6 ($0.74/M in, $3.49/M out via OpenRouter)
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

# Default to non-thinking K2 (original 0711). K2.6's thinking channel
# consumes the entire output budget on file-modification tickets, leaving
# no room for visible content. K2 with full-file output mode is reliable
# and ~5x cheaper. Override via KIMI_MODEL env var.
MODEL = os.environ.get("KIMI_MODEL", "moonshotai/kimi-k2")
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# OpenRouter pricing per million tokens (in / out)
_PRICING = {
    "moonshotai/kimi-k2":            (0.55, 2.20),
    "moonshotai/kimi-k2.5":          (0.74, 3.49),
    "moonshotai/kimi-k2.6":          (0.74, 3.49),
    "moonshotai/kimi-k2-thinking":   (0.60, 2.50),
}
_in_per_m, _out_per_m = _PRICING.get(MODEL, (0.74, 3.49))
PRICE_INPUT_PER_TOKEN = _in_per_m / 1_000_000
PRICE_OUTPUT_PER_TOKEN = _out_per_m / 1_000_000

# K2.6 burns ~3K reasoning tokens before visible content; allocate generously
# so the diff actually emerges. Per-ticket cap raised to match real spend.
PER_CALL_INPUT_TOKEN_CEILING = 25_000
PER_CALL_OUTPUT_TOKEN_CEILING = 10_000
PER_TICKET_USD_CAP = 0.50


# Patterns to scrub from upstream body excerpts before they land in disk
# logs / error messages. The OpenRouter response body is normally just a
# completion, but on error it can echo headers / our own request payload.
# Belt-and-suspenders: strip anything that looks like a credential before
# this string ever reaches summary.json.
_BODY_SCRUB_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),     "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}"),     "[REDACTED_OPENROUTER_KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),         "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"\bghp_[A-Za-z0-9]{30,}"),          "[REDACTED_GITHUB_PAT]"),
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),     "[REDACTED_AWS_KEY]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_.\-]{16,}",
                re.IGNORECASE),                       "Bearer [REDACTED_BEARER]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[REDACTED_JWT]"),
)


def _scrub_body_for_log(text: str) -> str:
    out = text
    for pat, repl in _BODY_SCRUB_PATTERNS:
        out = pat.sub(repl, out)
    return out


class BudgetExceeded(Exception):
    pass


class KimiError(Exception):
    pass


@dataclass
class CallUsage:
    input_tokens: int
    output_tokens: int
    cost_usd: float

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
        }


@dataclass
class TicketBudget:
    ticket_id: str
    spent_usd: float = 0.0
    calls: list[CallUsage] = field(default_factory=list)

    def record(self, usage: CallUsage) -> None:
        self.calls.append(usage)
        self.spent_usd += usage.cost_usd

    def remaining(self) -> float:
        return max(0.0, PER_TICKET_USD_CAP - self.spent_usd)

    def as_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "spent_usd": round(self.spent_usd, 6),
            "cap_usd": PER_TICKET_USD_CAP,
            "calls": [c.as_dict() for c in self.calls],
        }


class KimiClient:
    def __init__(self, api_key: str | None = None, *, timeout: int = 240) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise KimiError("OPENROUTER_API_KEY not set")
        self.timeout = timeout

    def call(
        self,
        *,
        ticket_budget: TicketBudget,
        system: str,
        user: str,
        max_tokens: int = PER_CALL_OUTPUT_TOKEN_CEILING,
        approx_input_tokens: int,
    ) -> tuple[str, CallUsage]:
        if approx_input_tokens > PER_CALL_INPUT_TOKEN_CEILING:
            raise BudgetExceeded(
                f"per-call input ceiling: {approx_input_tokens} > {PER_CALL_INPUT_TOKEN_CEILING}"
            )
        if max_tokens > PER_CALL_OUTPUT_TOKEN_CEILING:
            raise BudgetExceeded(
                f"per-call output ceiling: {max_tokens} > {PER_CALL_OUTPUT_TOKEN_CEILING}"
            )

        # Pre-flight cost projection at the per-call ceiling. If the ticket
        # can't afford a worst-case call, refuse before the network roundtrip.
        worst_case_cost = (
            approx_input_tokens * PRICE_INPUT_PER_TOKEN
            + max_tokens * PRICE_OUTPUT_PER_TOKEN
        )
        if ticket_budget.spent_usd + worst_case_cost > PER_TICKET_USD_CAP:
            raise BudgetExceeded(
                f"ticket {ticket_budget.ticket_id}: projected cost "
                f"{ticket_budget.spent_usd + worst_case_cost:.4f} would exceed cap "
                f"{PER_TICKET_USD_CAP}"
            )

        body = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        req = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/coffeethencode/urban-hazard-maps",
                "X-Title": "UHM ticket orchestrator",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            err_body = _scrub_body_for_log(e.read().decode("utf-8", "replace"))[:500]
            raise KimiError(f"OpenRouter HTTP {e.code}: {err_body}")
        except urllib.error.URLError as e:
            raise KimiError(f"OpenRouter unreachable: {e.reason}")
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as e:
            # Defensive: OpenRouter occasionally returns truncated/streamed bodies.
            # Scrub before persisting; the body can echo headers / our own
            # Authorization on certain error paths.
            self._last_raw_body = _scrub_body_for_log(raw_body)
            raise KimiError(
                f"OpenRouter returned non-JSON body ({len(raw_body)} bytes, "
                f"parse error at char {e.pos}): {self._last_raw_body[:500]!r}"
            )

        choices = payload.get("choices") or []
        if not choices:
            raise KimiError(f"empty choices: {payload!r}")
        message = choices[0].get("message") or {}
        # Kimi K2.6 sometimes splits its output: `content` may be null while
        # the real diff lands in `reasoning` (thinking-style channel) or in a
        # nested `tool_calls`. Fall back across all of them.
        content = message.get("content")
        if content is None or content == "":
            content = message.get("reasoning") or ""
        if not content:
            tool_calls = message.get("tool_calls") or []
            for tc in tool_calls:
                args = (tc.get("function") or {}).get("arguments") or ""
                if args:
                    content = args
                    break
        if not content:
            raise KimiError(
                f"empty content; finish_reason={choices[0].get('finish_reason')!r}; "
                f"raw={json.dumps(payload)[:1500]}"
            )

        usage_block = payload.get("usage") or {}
        in_tok = int(usage_block.get("prompt_tokens", approx_input_tokens))
        out_tok = int(usage_block.get("completion_tokens", 0))
        cost = in_tok * PRICE_INPUT_PER_TOKEN + out_tok * PRICE_OUTPUT_PER_TOKEN

        usage = CallUsage(input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost)
        ticket_budget.record(usage)
        # Stash the raw payload so callers can persist it BEFORE we surface
        # any budget exception that would short-circuit normal logging.
        self._last_raw_payload = payload
        if ticket_budget.spent_usd > PER_TICKET_USD_CAP:
            raise BudgetExceeded(
                f"ticket {ticket_budget.ticket_id}: spent "
                f"{ticket_budget.spent_usd:.4f} > cap {PER_TICKET_USD_CAP} "
                f"(post-call detection — refusing further retries)"
            )
        return content, usage
