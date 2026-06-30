"""CurrencyService — first-party FX normalization to the tenant base currency.

No external rate feed (§3.4 first-party only). Rates are a configured, first-party table
(or a provided per-record rate). Same-currency conversions are identity. All money math is
Decimal in Python (§5.6); the result feeds `spend_records.base_amount`/`fx_rate`.
"""

from __future__ import annotations

from decimal import Decimal

# First-party indicative rates → USD (configurable per tenant). NOT a market feed; these
# are the platform's stated assumptions, used only when a record carries no provided rate.
_RATES_TO_USD: dict[str, Decimal] = {
    "USD": Decimal("1"),
    "EUR": Decimal("1.08"),
    "GBP": Decimal("1.27"),
    "INR": Decimal("0.012"),
    "JPY": Decimal("0.0067"),
    "CAD": Decimal("0.74"),
    "AUD": Decimal("0.66"),
}


class CurrencyService:
    def to_base(
        self,
        amount: Decimal,
        currency: str,
        base_currency: str,
        *,
        provided_rate: Decimal | None = None,
    ) -> tuple[Decimal, Decimal]:
        """Return (base_amount, fx_rate). Same currency → identity. Unknown currency →
        passthrough at rate 1 (recorded so it can be flagged by the Data Steward)."""
        amount = Decimal(str(amount))
        if currency == base_currency:
            return amount, Decimal("1")
        if provided_rate is not None:
            rate = Decimal(str(provided_rate))
            return (amount * rate).quantize(Decimal("0.01")), rate

        from_usd = _RATES_TO_USD.get(currency)
        to_usd = _RATES_TO_USD.get(base_currency)
        if from_usd is None or to_usd is None:
            return amount, Decimal("1")  # unknown pair → passthrough (flagged downstream)
        rate = from_usd / to_usd  # cross rate: 1 unit of `currency` in `base_currency`
        return (amount * rate).quantize(Decimal("0.01")), rate.quantize(Decimal("0.000001"))


currency_service = CurrencyService()
