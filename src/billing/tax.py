"""Tax seam: the one place a billing country becomes a tax amount."""

# Basis points by country. Set "IN" to 1800 (18% GST) once GST-registered;
# export-tracked countries stay 0.
TAX_RATE_BPS_BY_COUNTRY: dict[str, int] = {"IN": 0}


def tax_amount_minor(amount_minor: int, country: str | None) -> int:
    rate_bps = TAX_RATE_BPS_BY_COUNTRY.get(country or "", 0)
    return amount_minor * rate_bps // 10_000
