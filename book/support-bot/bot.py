"""A deterministic SIMULATED support bot. It makes no network or LLM calls.

THIS IS A SIMULATOR. It stands in for a real agent so that the book's evidence
chain (module -> configuration -> evidence bundle -> gate decision) can be run
offline and reproducibly. Its formulas are invented for teaching: they do not
model any real LLM, and no number it produces is a measurement of a real bot.

Given a configuration (the four chapter 5 knobs) and a ticket, `run_bot`
returns whether the ticket was resolved, a cost in dollars, and a reply length
in tokens and a reply latency in milliseconds.

The formulas (all constants are in the tables below):

    p(resolve) = SKILL[model] - DIFFICULTY_PENALTY[difficulty]
                 + (lookup tickets only)  LOOKUP_PENALTY + LOOKUP_HELP * min(max_tool_calls, 2)
                 + RETRIEVAL_BONUS * use_retrieval
                 - TEMPERATURE_PENALTY * temperature          (clipped to [0.02, 0.98])
    resolved   = u < p(resolve)                               u ~ Uniform(0, 1)

    tools_used = min(max_tool_calls, 2) on lookup tickets, 0 on the others
    cost_usd   = (PRICE[model] + TOOL_COST * tools_used + RETRIEVAL_COST * use_retrieval)
                 * (1 + COST_NOISE * g_cost)                  g_cost ~ N(0, 1)
    reply_tokens = BASE_TOKENS[model] + RETRIEVAL_TOKENS * use_retrieval
                   + TEMPERATURE_TOKENS * temperature + TOOL_TOKENS * tools_used
                   + TOKEN_NOISE * g_tokens                   g_tokens ~ N(0, 1)
    latency_ms = (BASE_MS[model] + TOOL_MS * tools_used + RETRIEVAL_MS * use_retrieval)
                 * exp(LATENCY_SIGMA * g_latency)            g_latency ~ N(0, 1)

A reply is SLOW when latency_ms > SLO_MS. That predicate belongs to this
evaluator, not to TVL: a module's chance constraint names the event and caps
its rate, and the evaluator decides what counts as one.

Randomness: u, g_cost, g_tokens and g_latency are drawn from a generator seeded by
(seed, ticket id) only, never by the configuration. Two configurations run
with the same seed therefore see the same "luck" on the same ticket (common
random numbers). That is what makes a paired comparison on the same tickets
meaningful, and it makes every run exactly repeatable.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

SIMULATOR_NOTE = (
    "SYNTHETIC: produced by the simulator book/support-bot/bot.py on synthetic tickets. "
    "Not a measurement of any real bot or model."
)

SKILL = {"small": 0.50, "medium": 0.62, "large": 0.72}
DIFFICULTY_PENALTY = {"easy": 0.00, "medium": 0.12, "hard": 0.30}
LOOKUP_PENALTY = 0.30  # a lookup ticket is hard to resolve without calling a tool...
LOOKUP_HELP = 0.26  # ...and each tool call (up to two) recovers this much
RETRIEVAL_BONUS = 0.04
TEMPERATURE_PENALTY = 0.06

PRICE = {"small": 0.0030, "medium": 0.0090, "large": 0.0240}  # dollars per ticket
TOOL_COST = 0.0004  # dollars per tool call used
RETRIEVAL_COST = 0.0003
COST_NOISE = 0.08  # relative

BASE_TOKENS = {"small": 70.0, "medium": 110.0, "large": 170.0}
RETRIEVAL_TOKENS = 60.0  # quoting help articles makes replies longer
TEMPERATURE_TOKENS = 40.0
TOOL_TOKENS = 25.0
TOKEN_NOISE = 30.0

BASE_MS = {"small": 1200.0, "medium": 1800.0, "large": 3000.0}  # milliseconds per reply
TOOL_MS = 1200.0  # each tool call used waits for a lookup
RETRIEVAL_MS = 600.0
LATENCY_SIGMA = 0.30  # log-normal spread
SLO_MS = 10000.0  # a reply slower than this is a violation of the latency SLO


@dataclass(frozen=True)
class BotResult:
    resolved: bool
    cost_usd: float
    reply_tokens: float
    latency_ms: float

    @property
    def slow(self) -> bool:
        """The evaluator's violation predicate for the latency SLO."""
        return self.latency_ms > SLO_MS


def resolve_probability(config: dict, ticket: dict) -> float:
    p = SKILL[config["model"]] - DIFFICULTY_PENALTY[ticket["difficulty"]]
    if ticket["needs_lookup"]:
        p += -LOOKUP_PENALTY + LOOKUP_HELP * min(int(config["max_tool_calls"]), 2)
    if config["use_retrieval"]:
        p += RETRIEVAL_BONUS
    p -= TEMPERATURE_PENALTY * float(config["temperature"])
    return min(0.98, max(0.02, p))


def tools_used(config: dict, ticket: dict) -> int:
    return min(int(config["max_tool_calls"]), 2) if ticket["needs_lookup"] else 0


def median_latency_ms(config: dict, ticket: dict) -> float:
    retrieval = 1 if config["use_retrieval"] else 0
    return BASE_MS[config["model"]] + TOOL_MS * tools_used(config, ticket) + RETRIEVAL_MS * retrieval


def slow_probability(config: dict, ticket: dict) -> float:
    """P(latency_ms > SLO_MS) for this configuration and ticket, from the formula above."""
    z = math.log(SLO_MS / median_latency_ms(config, ticket)) / LATENCY_SIGMA
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def run_bot(config: dict, ticket: dict, seed: int) -> BotResult:
    """Simulate one attempt at one ticket. Deterministic in (config, ticket, seed)."""
    rng = random.Random(f"support-bot-sim:{seed}:{ticket['id']}")
    u = rng.random()
    g_cost = rng.gauss(0.0, 1.0)
    g_tokens = rng.gauss(0.0, 1.0)
    g_latency = rng.gauss(0.0, 1.0)  # drawn last, so the earlier draws are unchanged

    used = tools_used(config, ticket)
    retrieval = 1 if config["use_retrieval"] else 0
    cost = (PRICE[config["model"]] + TOOL_COST * used + RETRIEVAL_COST * retrieval) * (
        1.0 + COST_NOISE * g_cost
    )
    tokens = (
        BASE_TOKENS[config["model"]]
        + RETRIEVAL_TOKENS * retrieval
        + TEMPERATURE_TOKENS * float(config["temperature"])
        + TOOL_TOKENS * used
        + TOKEN_NOISE * g_tokens
    )
    return BotResult(
        resolved=u < resolve_probability(config, ticket),
        cost_usd=max(0.0, cost),
        reply_tokens=max(1.0, tokens),
        latency_ms=median_latency_ms(config, ticket) * math.exp(LATENCY_SIGMA * g_latency),
    )


def expected_resolution_rate(config: dict, tickets: list[dict]) -> float:
    """The simulator's own true resolution rate for `config` on `tickets` (no sampling noise).

    Because the formulas above are known, the scenarios can be checked against
    them: a candidate that is "truly better" really is, in the simulator.
    """
    return sum(resolve_probability(config, t) for t in tickets) / len(tickets)


def expected_slow_rate(config: dict, tickets: list[dict]) -> float:
    """The simulator's own true rate of slow replies for `config` on `tickets` (no sampling noise)."""
    return sum(slow_probability(config, t) for t in tickets) / len(tickets)
