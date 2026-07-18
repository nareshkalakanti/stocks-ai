"""P/CF helpers for H&T."""

from stocks.strategies.intrinsic_value.strategy import price_to_cash_flow


def test_price_to_cash_flow_from_yfinance_field():
    pcf = price_to_cash_flow({"priceToOperatingCashFlows": 12.5}, price=100.0)
    assert pcf == 12.5


def test_price_to_cash_flow_from_operating_cashflow():
    pcf = price_to_cash_flow(
        {
            "operatingCashflow": 500.0,
            "sharesOutstanding": 100.0,
        },
        price=250.0,
    )
    assert pcf == 50.0
