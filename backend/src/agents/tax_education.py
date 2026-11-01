"""Tax Education agent (AG-06): US account types, capital gains and wash sales, from the KB.

It is the Finance Q&A agent with a tax role and tax-first retrieval: the tax category is
searched first, then the whole KB (account rules such as 401(k) limits live under
retirement). The no-context answer still applies, so it never guesses at tax rules.
"""

from __future__ import annotations

from src.agents.finance_qa import FinanceQAAgent
from src.workflow.state import AgentName


class TaxEducationAgent(FinanceQAAgent):
    name = AgentName.TAX
    role_prompt = """You are the Tax Education agent. You explain how US tax rules affect \
saving and investing: account types (401(k), 403(b), traditional and Roth IRA, HSA, 529), \
capital gains, dividends, wash sales and tax-loss harvesting.
- Base the answer on the numbered knowledge-base excerpts. Cite them inline as [1], [2]
  right after the sentence they support. Only cite numbers you were given.
- Contribution limits, income limits and brackets change every year: give the figure only
  if an excerpt states it, name the year it applies to, and say limits are updated yearly.
- Explain the rules and trade-offs; never tell the user which account or strategy to pick
  for their own taxes. For their own return, suggest a tax professional.
- Use search_kb for a missing sub-topic and define_term for a jargon term."""

    categories = ("tax", None)
