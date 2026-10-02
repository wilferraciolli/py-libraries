from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import PlainSerializer


def money(value: Decimal | str | float | int) -> Decimal:
    """Round to two decimal places, half up (what Java's setScale(2, HALF_UP) does)."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# An amount of money: exact in Python, a plain JSON number on the wire (clients
# do arithmetic with it; Pydantic would otherwise send Decimal as a string).
Money = Annotated[Decimal, PlainSerializer(float, return_type=float)]
