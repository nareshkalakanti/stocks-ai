import pandas as pd


def safe_str(value, default: str = "") -> str:
    """Coerce CSV/DB values (including float NaN) to a stripped string."""
    if value is None:
        return default
    if isinstance(value, float) and pd.isna(value):
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.lower() == "nan":
        return default
    return text if text else default


def is_junk_company_name(name: str, ticker: str = "") -> bool:
    """True when a label looks like a yfinance symbol blob, not a company name."""
    text = safe_str(name)
    if not text:
        return True
    sym = safe_str(ticker).upper()
    upper = text.upper()
    if sym and upper == sym:
        return True
    if ".NS" in upper or ".BO" in upper:
        return True
    if "," in text:
        return True
    return False


def resolve_company_name(*candidates: str | None, ticker: str = "") -> str:
    """Pick the first human-readable company name, else fall back to ticker."""
    sym = safe_str(ticker).upper()
    for raw in candidates:
        name = safe_str(raw)
        if name and not is_junk_company_name(name, sym):
            return name
    return sym


def response_text(content) -> str:
    """Normalize LLM message content to a string."""
    if content is None:
        return ""
    return str(content).strip()


def format_indian_number(value: float, *, decimals: int = 0) -> str:
    """Format with Indian digit grouping (e.g. 12,34,567)."""
    if decimals < 0:
        decimals = 0
    rounded = round(float(value), decimals)
    if decimals:
        int_part = int(rounded)
        frac = abs(rounded - int_part)
        frac_digits = int(round(frac * 10**decimals))
        frac_str = f".{frac_digits:0{decimals}d}"
    else:
        int_part = int(round(rounded))
        frac_str = ""

    sign = "-" if int_part < 0 else ""
    digits = str(abs(int_part))
    if len(digits) <= 3:
        grouped = digits
    else:
        last3 = digits[-3:]
        rest = digits[:-3]
        parts: list[str] = []
        while rest:
            parts.append(rest[-2:])
            rest = rest[:-2]
        parts.reverse()
        grouped = ",".join(parts + [last3])
    return f"{sign}{grouped}{frac_str}"


def _coerce_market_cap_cr(value: object) -> float | None:
    """Normalize market cap to ₹ crore (handles legacy 'B' labels)."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s or s == "—":
            return None
        upper = s.upper().replace(",", "")
        if upper.endswith("L CR"):
            try:
                return float(upper[:-4].strip()) * 100_000
            except ValueError:
                return None
        if upper.endswith("CR"):
            try:
                return float(upper[:-2].strip())
            except ValueError:
                return None
        if upper.endswith("B"):
            try:
                return float(upper[:-1].strip()) * 100
            except ValueError:
                return None
    try:
        cr = float(value)
    except (TypeError, ValueError):
        return None
    return cr if cr > 0 else None


def format_market_cap_cr(value: object) -> str:
    """Indian market cap label — value is already in ₹ crore."""
    cr = _coerce_market_cap_cr(value)
    if cr is None:
        return "—"
    # 1 L Cr = 1 lakh crore = 100,000 Cr
    if cr >= 100_000:
        return f"{format_indian_number(cr / 100_000, decimals=2)} L Cr"
    if cr >= 1_000:
        return f"{format_indian_number(cr, decimals=0)} Cr"
    if cr >= 100:
        return f"{format_indian_number(cr, decimals=1)} Cr"
    return f"{format_indian_number(cr, decimals=1)} Cr"
