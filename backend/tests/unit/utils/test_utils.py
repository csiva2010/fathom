from __future__ import annotations

from src.utils.money import format_percent, format_usd
from src.utils.tokens import estimate_tokens, tokens_to_words


def test_money_formatting() -> None:
    assert format_usd(1234.5) == "$1,234.50"
    assert format_usd(-50, decimals=0) == "-$50"
    assert format_percent(1.234) == "1.23%"
    assert format_percent(2, signed=True) == "+2.00%"
    assert format_percent(-2, signed=True) == "-2.00%"


def test_token_estimates() -> None:
    assert estimate_tokens("one two three") == 4
    assert tokens_to_words(500) == 375
    assert tokens_to_words(0) == 1
