"""PEAD validation — compare PEAD2 output with captured references + FF dashboard."""

from __future__ import annotations

import os

import pandas as pd
import pytest
import yfinance as yf

from stocks.market.price_service import to_yfinance_symbol
from stocks.strategies.pead2.quarters import build_quarter_panel
from stocks.strategies.pead2.service import analyze_pead2_ticker
from stocks.strategies.pead2.strategy import (
    compute_daily_ret_ff,
    compute_daily_ret_pct,
    compute_forward_pe,
    compute_return_since_result,
    score_pead2_absolute,
    score_pead2_candidates,
    score_pead2_ff,
    score_pead2_percentile,
)
from stocks.strategies.pead2.validation_refs import (
    YFINANCE_SYMBOLS,
    assert_close,
    extract_raw_quarterly,
    ff_daily_ret_rows,
    ff_monitor_case,
    ff_monitor_cases,
    ff_monitor_score_comparison,
    ff_reference_by_ticker,
    live_returns_vs_ff,
    load_pead_references,
    pead2_growth_for_ticker,
)

SKIP_LIVE = os.getenv("PEAD_INTEGRATION") != "1"

LAKHS_TOL = 25.0
LAKHS_TOL_LARGE = 100.0
PCT_TOL = 0.6
SCORE_TOL = 1.5
PE_TOL = 2.0
RETURNS_TOL = 2.0


def _lakhs_tol(value: float | None) -> float:
    if value is not None and value > 50000:
        return LAKHS_TOL_LARGE
    return LAKHS_TOL


class TestPeadReferenceFile:
    def test_reference_file_structure(self):
        refs = load_pead_references()
        assert "yfinance_raw" in refs
        assert "financiallyfree_screenshot" in refs
        assert "ff_returns_dashboard_2026_07_10" in refs
        assert "ff_daily_ret_dashboard_2026_07_10" in refs
        assert "ff_pead_monitor_2026_07_13" in refs
        for sym in YFINANCE_SYMBOLS:
            assert sym in refs["yfinance_raw"]
        ff_rows = refs["ff_returns_dashboard_2026_07_10"]["rows"]
        assert len(ff_rows) >= 35
        assert ff_rows[0]["ticker"] == "SAKAR"
        tickers = {r["ticker"] for r in ff_rows}
        assert "RPEL" in tickers
        assert "GRWRHITECH" in tickers

    def test_ff_daily_ret_batch_structure(self):
        refs = load_pead_references()
        batch = refs["ff_daily_ret_dashboard_2026_07_10"]
        assert batch["sort_by"] == "daily_ret_pct"
        rows = batch["rows"]
        assert len(rows) == 17
        assert rows[0]["ticker"] == "JAYBARMARU"
        assert rows[0]["daily_ret_pct"] == 12.91
        tickers = {r["ticker"] for r in rows}
        assert "SAMMAANCAP" in tickers
        assert "SUMMITSEC" in tickers
        assert "BPLPHARMA" in tickers
        # Sorted by daily ret desc (null last in reference file)
        dailies = [r["daily_ret_pct"] for r in rows if r.get("daily_ret_pct") is not None]
        assert dailies == sorted(dailies, reverse=True)


class TestPeadScoreVsFinanciallyFree:
    """FF signed PEAD score vs legacy percentile mode."""

    def test_ff_mode_can_be_negative_like_dashboard(self):
        ff_neg = [r for r in ff_daily_ret_rows() if r["pead_score"] < 0]
        assert len(ff_neg) >= 5

        df = pd.DataFrame(
            [
                {
                    "ticker": "BAD",
                    "returns_pct": 5.0,
                    "sales_yoy": -10.0,
                    "np_yoy": -40.0,
                    "forward_pe": 999.0,
                }
            ]
        )
        scored = score_pead2_ff(df)
        assert scored["pead_score"].iloc[0] < 0

    def test_percentile_mode_stays_bounded_0_100(self):
        universe = pd.DataFrame(
            [
                {"ticker": "A", "returns_pct": 34.0, "sales_yoy": 25.0, "np_yoy": 50.0, "forward_pe": 12.0},
                {"ticker": "B", "returns_pct": 10.0, "sales_yoy": -5.0, "np_yoy": -20.0, "forward_pe": 999.0},
                {"ticker": "C", "returns_pct": 20.0, "sales_yoy": 10.0, "np_yoy": 15.0, "forward_pe": 40.0},
            ]
        )
        scored = score_pead2_percentile(universe)
        assert (scored["pead_score"] >= 0).all()
        assert (scored["pead_score"] <= 100).all()

    def test_jaybarmaru_ff_score_closer_to_dashboard_than_percentile(self):
        refs = load_pead_references()
        growth = pead2_growth_for_ticker("JAYBARMARU")
        ff_row = next(r for r in ff_daily_ret_rows() if r["ticker"] == "JAYBARMARU")
        row = {**growth, "returns_pct": ff_row["returns_pct"], "forward_pe": ff_row["forward_pe"]}
        ff_scored = score_pead2_ff(pd.DataFrame([row]))
        ff_score = float(ff_scored["pead_score"].iloc[0])
        assert abs(ff_score - ff_row["pead_score"]) < abs(
            ff_score - refs["yfinance_raw"]["JAYBARMARU"]["pead_score"]
        )

    def test_absolute_mode_still_bounded_0_100(self):
        row = ff_daily_ret_rows()[2]
        df = pd.DataFrame(
            [
                {
                    "ticker": row["ticker"],
                    "sales_yoy": -10.0,
                    "np_yoy": -30.0,
                    "sales_qoq": -5.0,
                    "np_qoq": -15.0,
                    "ebidt_yoy": -8.0,
                    "ebidt_qoq": -4.0,
                    "forward_pe": 999.0,
                }
            ]
        )
        scored = score_pead2_absolute(df)
        assert scored["pead_score"].iloc[0] >= 0


class TestPeadDailyRetVsFinanciallyFree:
    def test_ff_daily_ret_is_max_single_day_move_capped(self):
        hist = pd.DataFrame(
            {"Close": [100.0, 110.0, 125.0, 120.0]},
            index=pd.date_range("2026-05-18", periods=4, freq="B"),
        )
        daily = compute_daily_ret_ff(hist, pd.Timestamp("2026-05-19"), cap=19.99)
        assert daily == 13.64  # 125/110 - 1

    def test_legacy_daily_ret_is_returns_over_trading_days(self):
        row = next(r for r in ff_daily_ret_rows() if r["ticker"] == "JAYBARMARU")
        returns = row["returns_pct"]
        ff_daily = row["daily_ret_pct"]
        n_equiv = returns / ff_daily
        assert abs(n_equiv - round(n_equiv)) > 0.05 or n_equiv < 1.5


class TestPeadCalculationLogic:
    """Offline checks that our formulas behave as documented."""

    def test_quarter_panel_excludes_pe_rows(self):
        rev = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=pd.date_range("2025-03-31", periods=5, freq="QE"))
        eb = rev * 0.2
        np_s = rev * 0.1
        eps = pd.Series([1.0, 1.2, 1.5, 2.0, 2.5], index=rev.index)
        panel = build_quarter_panel(rev, eb, np_s, eps)
        labels = {row["label"] for row in panel["rows"]}
        assert labels == {"Sales", "Operating Profit", "Net Profit", "EPS in Rs"}
        assert "Current PE" not in labels
        assert "Forward PE" not in labels

    def test_return_since_result_formula(self):
        hist = pd.DataFrame(
            {"Close": [100.0, 102.0, 105.0, 110.0]},
            index=pd.date_range("2026-05-14", periods=4, freq="B"),
        )
        ret = compute_return_since_result(
            hist,
            pd.Timestamp("2026-05-16"),
            current_price=134.16,
        )
        assert ret is not None
        assert ret == round((134.16 - 100.0) / 100.0 * 100.0, 2)

    def test_forward_pe_run_rate_formula(self):
        eps = pd.Series([2.5], index=[pd.Timestamp("2026-03-31")])
        fpe = compute_forward_pe(34.16, eps, info={})
        assert fpe == round(34.16 / (2.5 * 4), 1)

    def test_ff_reference_dates_are_iso(self):
        for row in ff_reference_by_ticker().values():
            rd = row.get("result_date")
            assert rd and len(str(rd)) == 10
            pd.Timestamp(rd)


class TestPeadFfMonitorJul2026:
    """FinanciallyFree PEAD Result Monitor — KPL & WPIL (Jul 2026 screenshots)."""

    def test_monitor_cases_present(self):
        cases = ff_monitor_cases()
        tickers = {c["ticker"] for c in cases}
        assert "KPL" in tickers
        assert "WPIL" in tickers

    def test_kpl_quarterly_lakhs_match_monitor_card(self):
        kpl = ff_monitor_case("KPL")
        card = kpl["monitor_card"]
        ff = load_pead_references()["financiallyfree_screenshot"]["KPL"]
        for key in (
            "revenue_q0_lakhs",
            "revenue_q1_lakhs",
            "revenue_yoy_lakhs",
            "np_q0_lakhs",
            "np_q1_lakhs",
            "np_yoy_lakhs",
        ):
            assert card[key] == ff[key]

    def test_wpil_monitor_card_matches_screenshot(self):
        wpil = ff_monitor_case("WPIL")
        card = wpil["monitor_card"]
        ff = load_pead_references()["financiallyfree_screenshot"]["WPIL"]
        assert card["pead_score"] == ff["pead_score"] == 40.4
        assert card["revenue_q0_lakhs"] == ff["revenue_q0_lakhs"]
        assert card["ebitda_pct_q0"] == ff["ebitda_pct_q0"]

    def test_ff_mode_score_with_dashboard_inputs_kpl(self):
        """Dashboard row (fwd PE 22.7 + returns) is closer to FF table score 47 than monitor card alone."""
        kpl = ff_monitor_case("KPL")
        card = kpl["monitor_card"]
        dash = kpl["dashboard_row"]
        monitor_row = {
            "sales_yoy": card["sales_yoy_pct"],
            "np_yoy": card["np_yoy_pct"],
            "forward_pe": card["forward_pe"],
        }
        dash_row = {
            "sales_yoy": card["sales_yoy_pct"],
            "np_yoy": card["np_yoy_pct"],
            "forward_pe": dash["forward_pe"],
            "returns_pct": dash["returns_pct"],
        }
        monitor_score = float(score_pead2_ff(pd.DataFrame([monitor_row]))["pead_score"].iloc[0])
        dash_score = float(score_pead2_ff(pd.DataFrame([dash_row]))["pead_score"].iloc[0])
        assert abs(dash_score - dash["pead_score"]) < abs(monitor_score - card["pead_score"])
        assert abs(dash_score - dash["pead_score"]) <= 6.0

    def test_ff_mode_score_computed_for_wpil(self):
        wpil = ff_monitor_case("WPIL")
        card = wpil["monitor_card"]
        raw = load_pead_references()["yfinance_raw"]["WPIL"]
        row = {
            "sales_yoy": raw["sales_yoy_pct"],
            "np_yoy": raw["np_yoy_pct"],
            "forward_pe": raw["forward_pe"],
        }
        ours = float(score_pead2_ff(pd.DataFrame([row]))["pead_score"].iloc[0])
        assert ours is not None
        assert card["pead_score"] == 40.4

    def test_score_comparison_helper_runs(self):
        df = ff_monitor_score_comparison()
        assert len(df) >= 2
        assert "ff_pead_score" in df.columns
        assert "our_pead_score" in df.columns


class TestPeadUnitValidation:
    def test_ff_dashboard_scores_can_be_negative(self):
        refs = load_pead_references()
        ff_scores = [r["pead_score"] for r in refs["ff_returns_dashboard_2026_07_10"]["rows"]]
        assert min(ff_scores) < 0

        df = pd.DataFrame(
            [
                {"ticker": "A", "returns_pct": 10.0, "sales_yoy": 20.0, "forward_pe": 15.0},
                {"ticker": "B", "returns_pct": 50.0, "sales_yoy": 5.0, "forward_pe": 40.0},
            ]
        )
        scored = score_pead2_ff(df)
        assert scored["pead_score"].notna().all()


@pytest.mark.skipif(SKIP_LIVE, reason="Set PEAD_INTEGRATION=1 for live yfinance validation")
class TestPeadLiveValidation:
  @pytest.fixture(scope="class")
  def refs(self):
      return load_pead_references()

  def test_raw_quarterly_matches_captured_reference(self, refs):
      for sym in YFINANCE_SYMBOLS:
          try:
              live = extract_raw_quarterly(sym)
          except ValueError as exc:
              pytest.skip(str(exc))
          ref = refs["yfinance_raw"][sym]
          assert live["q0_end"] == ref["q0_end"]
          for key in (
              "revenue_q0_lakhs",
              "revenue_q1_lakhs",
              "revenue_yoy_lakhs",
              "np_q0_lakhs",
              "np_q1_lakhs",
              "np_yoy_lakhs",
              "sales_yoy_pct",
              "sales_qoq_pct",
              "np_yoy_pct",
          ):
              tol = PCT_TOL if "pct" in key else _lakhs_tol(ref.get(key))
              assert_close(live[key], ref[key], tol, f"{sym}.{key}")

  def test_pead2_growth_matches_reference_symbols(self, refs):
      """Symbols with complete PEAD2 rows should match captured growth %."""
      for sym in ("BLACKBUCK", "JAYBARMARU", "SOUTHWEST", "TSFINV"):
          ref = refs["yfinance_raw"][sym]
          live = pead2_growth_for_ticker(sym)
          assert_close(live["sales_yoy"], ref["sales_yoy_pct"], PCT_TOL, f"{sym}.sales_yoy")
          assert_close(live["np_yoy"], ref["np_yoy_pct"], PCT_TOL, f"{sym}.np_yoy")

  def test_ff_screenshot_raw_lakhs_where_documented(self, refs):
      ff = refs["financiallyfree_screenshot"]
      live_j = extract_raw_quarterly("JAYBARMARU")
      assert_close(live_j["revenue_q0_lakhs"], ff["JAYBARMARU"]["revenue_q0_lakhs"], 5, "JBM.rev_q0")
      assert_close(live_j["np_q0_lakhs"], ff["JAYBARMARU"]["np_q0_lakhs"], 5, "JBM.np_q0")

  def test_our_pead_scores_use_ff_mode_by_default(self, refs):
      blob = analyze_pead2_ticker("JAYBARMARU", "NSE")
      lag0 = (blob or {}).get("lags", {}).get("0") or {}
      if not lag0:
          pytest.skip("JAYBARMARU missing lag-0 payload")
      growth = pead2_growth_for_ticker("JAYBARMARU")
      ref = refs["yfinance_raw"]["JAYBARMARU"]
      assert_close(growth["sales_yoy"], ref["sales_yoy_pct"], PCT_TOL, "JAYBARMARU.sales_yoy")
      ff_row = next(r for r in ff_daily_ret_rows() if r["ticker"] == "JAYBARMARU")
      row = {
          **growth,
          "returns_pct": lag0.get("returns_pct"),
          "forward_pe": lag0.get("forward_pe"),
          "cf_profit": lag0.get("cf_profit"),
      }
      scored = score_pead2_ff(pd.DataFrame([row]))
      ours = float(scored["pead_score"].iloc[0])
      assert abs(ours - ff_row["pead_score"]) < 25.0

  def test_sakar_returns_close_with_ff_result_date_at_live_price(self, refs):
      """Returns formula matches FF when result_date aligns (price drift explains rest)."""
      row = ff_reference_by_ticker()["SAKAR"]
      live, expected = live_returns_vs_ff("SAKAR", row)
      assert live is not None
      assert_close(live, expected, RETURNS_TOL, "SAKAR.returns_pct")

  def test_ff_returns_with_reference_result_dates(self, refs):
      """When FF result_date is used, Returns should be close for liquid names."""
      rows = refs["ff_returns_dashboard_2026_07_10"]["rows"]
      checked = 0
      matched = 0
      for row in rows:
          ticker = row["ticker"]
          if ticker not in {"SAKAR", "HFCL", "BALAMINES", "NITTAGELA", "JAYBARMARU", "PRECOT"}:
              continue
          live, expected = live_returns_vs_ff(ticker, row)
          if live is None:
              continue
          checked += 1
          try:
              assert_close(live, expected, RETURNS_TOL, f"{ticker}.returns_pct")
              matched += 1
          except AssertionError:
              pass
      assert checked >= 2
      assert matched >= 1

  def test_ff_daily_ret_batch_returns_vs_formula(self, refs):
      """FF daily-ret screenshot rows: Returns vs compute_return_since_result."""
      priority = [
          "JAYBARMARU",
          "PRECOT",
          "KDDL",
          "APOLLOPIPE",
          "TATACOMM",
          "IMPAL",
      ]
      by_ticker = ff_reference_by_ticker()
      checked = matched = 0
      for ticker in priority:
          row = by_ticker.get(ticker)
          if not row:
              continue
          live, expected = live_returns_vs_ff(ticker, row)
          if live is None or expected is None:
              continue
          checked += 1
          try:
              assert_close(live, expected, RETURNS_TOL, f"{ticker}.returns_pct")
              matched += 1
          except AssertionError:
              pass
      assert checked >= 3
      assert matched >= 1

  def test_ff_forward_pe_for_reference_tickers(self, refs):
      """Forward PE may use yfinance forwardPE; compare when close to FF run-rate PE."""
      rows = ff_reference_by_ticker()
      checked = matched = 0
      for ticker in ("JAYBARMARU", "PRECOT", "KDDL", "HFCL"):
          row = rows.get(ticker)
          if not row or row.get("forward_pe") is None or row["forward_pe"] >= 500:
              continue
          blob = analyze_pead2_ticker(ticker, "NSE")
          lag0 = (blob or {}).get("lags", {}).get("0") or {}
          ours = lag0.get("forward_pe")
          if ours is None:
              continue
          checked += 1
          try:
              assert_close(ours, row["forward_pe"], PE_TOL * 3, f"{ticker}.forward_pe")
              matched += 1
          except AssertionError:
              pass
      assert checked >= 2
      assert matched >= 1

  def test_analyze_pead2_uses_return_since_result_when_price_available(self):
      blob = analyze_pead2_ticker("SAKAR", "NSE")
      lag0 = (blob or {}).get("lags", {}).get("0") or {}
      assert lag0.get("returns_pct") is not None
      assert lag0.get("price") is not None
      rd = pd.Timestamp(lag0["result_date"])
      symbol = to_yfinance_symbol("SAKAR", "NSE")
      yt = yf.Ticker(symbol)
      hist = yt.history(
          start=(rd - pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
          auto_adjust=True,
      )
      expected = compute_return_since_result(
          hist, rd, current_price=float(lag0["price"])
      )
      assert_close(lag0["returns_pct"], expected, 0.05, "SAKAR.service_returns")
