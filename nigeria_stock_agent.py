"""
Nigeria Stock Market Analysis Agent
Analyzes NGX-listed stocks and predicts top 10 investments using Claude claude-opus-4-7.
"""

import os
import sys
import json
import warnings
from datetime import datetime
from typing import Optional, Dict, List, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
import anthropic
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

NGX_STOCKS = {
    "ZENITHBANK.LG": {"name": "Zenith Bank", "sector": "Banking"},
    "GTCO.LG": {"name": "GT Holdings", "sector": "Banking"},
    "ACCESS.LG": {"name": "Access Holdings", "sector": "Banking"},
    "FBNH.LG": {"name": "FBN Holdings", "sector": "Banking"},
    "UBA.LG": {"name": "United Bank for Africa", "sector": "Banking"},
    "STANBIC.LG": {"name": "Stanbic IBTC", "sector": "Banking"},
    "FIDELITYBK.LG": {"name": "Fidelity Bank", "sector": "Banking"},
    "FCMB.LG": {"name": "FCMB Group", "sector": "Banking"},
    "MTNN.LG": {"name": "MTN Nigeria", "sector": "Telecom"},
    "AIRTELAFRI.LG": {"name": "Airtel Africa", "sector": "Telecom"},
    "NESTLE.LG": {"name": "Nestlé Nigeria", "sector": "Consumer Goods"},
    "NB.LG": {"name": "Nigerian Breweries", "sector": "Consumer Goods"},
    "BUAFOODS.LG": {"name": "BUA Foods", "sector": "Consumer Goods"},
    "GUINNESS.LG": {"name": "Guinness Nigeria", "sector": "Consumer Goods"},
    "UNILEVER.LG": {"name": "Unilever Nigeria", "sector": "Consumer Goods"},
    "DANGCEM.LG": {"name": "Dangote Cement", "sector": "Industrial"},
    "BUACEMENT.LG": {"name": "BUA Cement", "sector": "Industrial"},
    "WAPCO.LG": {"name": "Lafarge Africa", "sector": "Industrial"},
    "SEPLAT.LG": {"name": "Seplat Energy", "sector": "Oil & Gas"},
    "OANDO.LG": {"name": "Oando PLC", "sector": "Oil & Gas"},
    "TRANSCORP.LG": {"name": "Transcorp Holdings", "sector": "Conglomerate"},
    "FLOUR.LG": {"name": "Flour Mills of Nigeria", "sector": "Consumer Goods"},
    "AIICO.LG": {"name": "AIICO Insurance", "sector": "Insurance"},
}


# ---------------------------------------------------------------------------
# Technical Indicator Implementations
# ---------------------------------------------------------------------------

def compute_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_macd(series: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = compute_ema(series, 12)
    ema26 = compute_ema(series, 26)
    macd_line = ema12 - ema26
    signal_line = compute_ema(macd_line, 9)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_bollinger_bands(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    sma = compute_sma(series, period)
    std = series.rolling(window=period).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    return upper, sma, lower


def compute_stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> Tuple[pd.Series, pd.Series]:
    lowest_low = low.rolling(window=period).min()
    highest_high = high.rolling(window=period).max()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    pct_k = 100 * (close - lowest_low) / denom
    pct_d = pct_k.rolling(window=3).mean()
    return pct_k, pct_d


def compute_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(window=period).mean()


# ---------------------------------------------------------------------------
# Data Fetching
# ---------------------------------------------------------------------------

def fetch_stock_data(ticker: str, period: str = "2y") -> Optional[pd.DataFrame]:
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period)
        if df.empty or len(df) < 60:
            return None
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return None


def fetch_fundamentals(ticker: str) -> Dict:
    defaults = {
        "pe_ratio": None,
        "pb_ratio": None,
        "roe": None,
        "revenue_growth": None,
        "profit_margin": None,
        "dividend_yield": None,
        "debt_to_equity": None,
        "market_cap": None,
        "current_ratio": None,
        "eps": None,
    }
    try:
        info = yf.Ticker(ticker).info
        return {
            "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
            "pb_ratio": info.get("priceToBook"),
            "roe": info.get("returnOnEquity"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margin": info.get("profitMargins"),
            "dividend_yield": info.get("dividendYield"),
            "debt_to_equity": info.get("debtToEquity"),
            "market_cap": info.get("marketCap"),
            "current_ratio": info.get("currentRatio"),
            "eps": info.get("trailingEps"),
        }
    except Exception:
        return defaults


# ---------------------------------------------------------------------------
# Scoring Engine
# ---------------------------------------------------------------------------

def compute_technical_score(df: pd.DataFrame) -> Dict:
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    signals = {}
    score_parts = []

    # --- Trend vs SMAs (20%) ---
    sma20 = compute_sma(close, 20).iloc[-1]
    sma50 = compute_sma(close, 50).iloc[-1]
    sma200 = compute_sma(close, 200).iloc[-1] if len(close) >= 200 else None
    current_price = close.iloc[-1]

    trend_score = 0
    if current_price > sma20:
        trend_score += 33
    if current_price > sma50:
        trend_score += 33
    if sma200 is not None and current_price > sma200:
        trend_score += 34
    elif sma200 is None:
        trend_score = int(trend_score * 1.5)
    trend_score = min(trend_score, 100)
    score_parts.append(("trend", trend_score, 0.20))
    signals["trend"] = "BULLISH" if trend_score >= 60 else "NEUTRAL" if trend_score >= 30 else "BEARISH"

    # --- RSI (15%) ---
    rsi = compute_rsi(close).iloc[-1]
    if np.isnan(rsi):
        rsi_score = 50
    elif 40 <= rsi <= 60:
        rsi_score = 80
    elif 30 <= rsi < 40 or 60 < rsi <= 70:
        rsi_score = 60
    elif rsi < 30:
        rsi_score = 90
    else:
        rsi_score = 20
    score_parts.append(("rsi", rsi_score, 0.15))
    signals["rsi"] = round(rsi, 2) if not np.isnan(rsi) else None

    # --- MACD (15%) ---
    macd_line, signal_line, histogram = compute_macd(close)
    macd_val = macd_line.iloc[-1]
    hist_val = histogram.iloc[-1]
    hist_prev = histogram.iloc[-2] if len(histogram) > 1 else 0

    macd_score = 50
    if macd_val > signal_line.iloc[-1]:
        macd_score += 25
    if hist_val > 0:
        macd_score += 15
    if hist_val > hist_prev:
        macd_score += 10
    macd_score = min(macd_score, 100)
    score_parts.append(("macd", macd_score, 0.15))
    signals["macd"] = "BULLISH" if macd_score >= 65 else "BEARISH"

    # --- Bollinger Band position (10%) ---
    bb_upper, bb_mid, bb_lower = compute_bollinger_bands(close)
    bb_pos = (current_price - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1] + 1e-9)
    bb_score = 100 - abs(bb_pos - 0.5) * 200
    bb_score = max(0, min(bb_score, 100))
    score_parts.append(("bollinger", bb_score, 0.10))
    signals["bb_position"] = round(bb_pos, 3)

    # --- Volume (10%) ---
    avg_vol_20 = volume.rolling(20).mean().iloc[-1]
    recent_vol = volume.iloc[-5:].mean()
    vol_ratio = recent_vol / avg_vol_20 if avg_vol_20 > 0 else 1
    vol_score = min(vol_ratio * 60, 100)
    score_parts.append(("volume", vol_score, 0.10))
    signals["volume_ratio"] = round(vol_ratio, 2)

    # --- Stochastic (10%) ---
    pct_k, pct_d = compute_stochastic(high, low, close)
    stoch_k = pct_k.iloc[-1]
    stoch_d = pct_d.iloc[-1]
    stoch_score = 50
    if not np.isnan(stoch_k):
        if stoch_k < 20:
            stoch_score = 85
        elif stoch_k > 80:
            stoch_score = 20
        else:
            stoch_score = 60
        if stoch_k > stoch_d:
            stoch_score = min(stoch_score + 15, 100)
    score_parts.append(("stochastic", stoch_score, 0.10))
    signals["stochastic_k"] = round(stoch_k, 2) if not np.isnan(stoch_k) else None

    # --- Price momentum (20%) ---
    ret_1m = (close.iloc[-1] / close.iloc[-22] - 1) * 100 if len(close) >= 22 else 0
    ret_3m = (close.iloc[-1] / close.iloc[-66] - 1) * 100 if len(close) >= 66 else 0
    ret_6m = (close.iloc[-1] / close.iloc[-132] - 1) * 100 if len(close) >= 132 else 0
    mom_score = 50
    mom_score += min(ret_1m * 1.5, 15)
    mom_score += min(ret_3m * 0.8, 20)
    mom_score += min(ret_6m * 0.5, 15)
    mom_score = max(0, min(mom_score, 100))
    score_parts.append(("momentum", mom_score, 0.20))
    signals["return_1m"] = round(ret_1m, 2)
    signals["return_3m"] = round(ret_3m, 2)
    signals["return_6m"] = round(ret_6m, 2)

    total_score = sum(s * w for _, s, w in score_parts)
    bullish_count = sum(1 for _, s, _ in score_parts if s >= 60)
    trend_label = "BULLISH" if bullish_count >= 4 else "NEUTRAL" if bullish_count >= 2 else "BEARISH"

    return {
        "score": round(total_score, 2),
        "signals": signals,
        "trend": trend_label,
        "current_price": round(current_price, 4),
    }


def compute_fundamental_score(fundamentals: Dict) -> Dict:
    score = 50
    details = {}

    pe = fundamentals.get("pe_ratio")
    if pe is not None:
        if 5 <= pe <= 15:
            score += 15
        elif 15 < pe <= 25:
            score += 8
        elif pe < 5:
            score += 5
        else:
            score -= 5
        details["pe_ratio"] = round(pe, 2)

    roe = fundamentals.get("roe")
    if roe is not None:
        roe_pct = roe * 100 if roe < 1 else roe
        if roe_pct >= 20:
            score += 15
        elif roe_pct >= 10:
            score += 8
        elif roe_pct >= 0:
            score += 2
        else:
            score -= 8
        details["roe_pct"] = round(roe_pct, 2)

    rev_growth = fundamentals.get("revenue_growth")
    if rev_growth is not None:
        rg = rev_growth * 100 if abs(rev_growth) < 1 else rev_growth
        if rg >= 20:
            score += 10
        elif rg >= 10:
            score += 6
        elif rg >= 0:
            score += 2
        else:
            score -= 5
        details["revenue_growth_pct"] = round(rg, 2)

    margin = fundamentals.get("profit_margin")
    if margin is not None:
        mg = margin * 100 if abs(margin) < 1 else margin
        if mg >= 20:
            score += 10
        elif mg >= 10:
            score += 5
        elif mg >= 0:
            score += 1
        else:
            score -= 8
        details["profit_margin_pct"] = round(mg, 2)

    div_yield = fundamentals.get("dividend_yield")
    if div_yield is not None:
        dy = div_yield * 100 if div_yield < 1 else div_yield
        if dy >= 5:
            score += 8
        elif dy >= 2:
            score += 5
        details["dividend_yield_pct"] = round(dy, 2)

    de = fundamentals.get("debt_to_equity")
    if de is not None:
        if de < 0.5:
            score += 8
        elif de < 1.5:
            score += 3
        elif de > 3:
            score -= 8
        details["debt_to_equity"] = round(de, 2)

    score = max(0, min(score, 100))
    if score >= 75:
        grade = "A"
    elif score >= 60:
        grade = "B"
    elif score >= 45:
        grade = "C"
    else:
        grade = "D"

    return {"score": round(score, 2), "grade": grade, "details": details}


def analyze_stock(ticker: str, name: str, sector: str) -> Optional[Dict]:
    print(f"  Analyzing {name} ({ticker})...", end=" ", flush=True)
    df = fetch_stock_data(ticker)
    if df is None:
        print("No data")
        return None

    tech = compute_technical_score(df)
    fundamentals = fetch_fundamentals(ticker)
    fund = compute_fundamental_score(fundamentals)

    composite = round(tech["score"] * 0.55 + fund["score"] * 0.45, 2)

    volatility = None
    if len(df) >= 20:
        returns = df["Close"].pct_change().dropna()
        volatility = round(returns.std() * np.sqrt(252) * 100, 2)

    print(f"Score={composite:.1f} | Tech={tech['score']:.1f} | Fund={fund['score']:.1f}")
    return {
        "ticker": ticker,
        "name": name,
        "sector": sector,
        "composite_score": composite,
        "technical_score": tech["score"],
        "fundamental_score": fund["score"],
        "trend": tech["trend"],
        "current_price": tech["current_price"],
        "signals": tech["signals"],
        "fundamentals": fundamentals,
        "fundamental_grade": fund["grade"],
        "fundamental_details": fund["details"],
        "annual_volatility_pct": volatility,
    }


# ---------------------------------------------------------------------------
# Agent Class
# ---------------------------------------------------------------------------

class NigeriaStockAgent:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-opus-4-7"

    def run_screening(self) -> List[Dict]:
        print("\n[Phase 1] Quantitative Screening of NGX Stocks")
        print("=" * 60)
        results = []
        for ticker, meta in NGX_STOCKS.items():
            result = analyze_stock(ticker, meta["name"], meta["sector"])
            if result:
                results.append(result)

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return results

    def generate_ai_analysis(self, top_stocks: List[Dict]) -> str:
        print("\n[Phase 2] Claude claude-opus-4-7 Deep Analysis (streaming)...")
        print("=" * 60)

        stock_data_str = json.dumps(
            [
                {
                    "rank": i + 1,
                    "ticker": s["ticker"],
                    "name": s["name"],
                    "sector": s["sector"],
                    "composite_score": s["composite_score"],
                    "technical_score": s["technical_score"],
                    "fundamental_score": s["fundamental_score"],
                    "trend": s["trend"],
                    "current_price_ngn": s["current_price"],
                    "annual_volatility_pct": s["annual_volatility_pct"],
                    "fundamental_grade": s["fundamental_grade"],
                    "signals": s["signals"],
                    "fundamentals": s["fundamentals"],
                    "fundamental_details": s["fundamental_details"],
                }
                for i, s in enumerate(top_stocks)
            ],
            indent=2,
        )

        prompt = f"""You are a senior Nigerian capital markets analyst with 20 years of experience on the NGX (Nigerian Exchange Group).
You have been given quantitative screening data for the top 10 Nigerian stocks ranked by a composite scoring model
(55% technical, 45% fundamental). Today's date is {datetime.now().strftime('%B %d, %Y')}.

QUANTITATIVE DATA:
{stock_data_str}

Perform a COMPREHENSIVE deep-dive analysis for each of these 10 stocks. For every stock you MUST:

1. **Executive Summary** – 3-4 sentences on why this stock is in the top 10.
2. **Technical Analysis** – Interpret the RSI, MACD, momentum, volume, and trend signals in the context of current NGX market conditions.
3. **Fundamental Analysis** – Evaluate PE ratio, ROE, revenue growth, profit margins, dividend yield, and debt levels. Compare to sector peers where relevant.
4. **Macro & Sector Tailwinds/Headwinds** – Nigeria-specific factors: CBN monetary policy, FX (naira), oil prices, inflation, regulatory environment, sector dynamics.
5. **Risk Assessment** – Key risks with probability and severity ratings.
6. **Investment Thesis** – The core bull case for each stock.
7. **Confidence Level** – Express your overall confidence as a percentage. Only recommend stocks where confidence ≥ 85%. If a stock falls below 85% confidence, explicitly state this and explain why.
8. **Price Target Range** – Provide a plausible 12-month price target range in NGN.

After analyzing all 10 stocks, provide:
- A **Portfolio Construction** section: how to optimally allocate across these 10 stocks (% weights, diversification rationale).
- A **Market Outlook** section: overall NGX outlook for 2025-2026.

Be specific, use actual data from the quantitative inputs, cite specific metrics, and provide institutional-quality analysis.
Confidence levels must be honest — if the data is mixed, say so and provide a nuanced view rather than inflating confidence."""

        collected_text = []
        with self.client.messages.stream(
            model=self.model,
            max_tokens=10000,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                collected_text.append(text)

        print("\n")
        return "".join(collected_text)

    def generate_timeframe_summary(self, top_stocks: List[Dict]) -> str:
        print("\n[Phase 3] Generating Timeframe Summary Table...")
        print("=" * 60)

        stock_list = "\n".join(
            f"{i+1}. {s['name']} ({s['ticker']}) — Sector: {s['sector']}, "
            f"Composite Score: {s['composite_score']}, Trend: {s['trend']}, "
            f"Vol: {s['annual_volatility_pct']}%"
            for i, s in enumerate(top_stocks)
        )

        prompt = f"""You are a Nigerian capital markets analyst. Given these top 10 NGX stocks (today: {datetime.now().strftime('%B %d, %Y')}):

{stock_list}

Create a structured investment timeframe analysis table. For each stock provide:

SHORT-TERM (1–3 months):
- Expected return range (%)
- Primary catalyst
- Confidence level (must be ≥ 85% to recommend; if below, flag as "Monitor Only")
- Risk level (Low/Medium/High)

MEDIUM-TERM (3–12 months):
- Expected return range (%)
- Primary catalyst
- Confidence level (must be ≥ 85% to recommend; if below, flag as "Monitor Only")
- Risk level (Low/Medium/High)

LONG-TERM (1–3 years):
- Expected return range (%)
- Primary catalyst
- Confidence level (must be ≥ 85% to recommend; if below, flag as "Monitor Only")
- Risk level (Low/Medium/High)

Format each stock as a clear section with a summary table. Be honest — if macro uncertainty reduces confidence below 85% for a particular timeframe, say so explicitly.

End with an "Overall Timeframe Recommendation" section that tells investors which stocks are best suited for which investment horizon."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )

        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""

    def _compile_report(
        self, all_results: List[Dict], ai_analysis: str, timeframe_table: str
    ) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        top10 = all_results[:10]
        total_analyzed = len(all_results)

        sector_counts: Dict[str, int] = {}
        for r in all_results:
            sector_counts[r["sector"]] = sector_counts.get(r["sector"], 0) + 1

        lines = []
        lines.append("=" * 80)
        lines.append("NIGERIA STOCK MARKET — AI-POWERED INVESTMENT ANALYSIS REPORT")
        lines.append(f"Generated: {timestamp}")
        lines.append(f"Model: Claude claude-opus-4-7 | NGX Listed Securities")
        lines.append("=" * 80)
        lines.append("")

        # ---- Section 1: Screening Overview ----
        lines.append("SECTION 1: QUANTITATIVE SCREENING OVERVIEW")
        lines.append("-" * 80)
        lines.append(f"Stocks Analyzed: {total_analyzed}")
        lines.append(f"Stocks Qualifying for Top 10: 10")
        lines.append("")
        lines.append("Sector Breakdown (All Analyzed):")
        for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {sector:<25} {count} stock(s)")
        lines.append("")
        lines.append("TOP 10 QUANTITATIVE RANKING TABLE")
        lines.append("-" * 80)
        header = f"{'Rank':<5} {'Ticker':<15} {'Name':<28} {'Sector':<18} {'Composite':>9} {'Tech':>6} {'Fund':>6} {'Trend':<10} {'Volatility':>10}"
        lines.append(header)
        lines.append("-" * len(header))
        for i, s in enumerate(top10, 1):
            vol_str = f"{s['annual_volatility_pct']}%" if s["annual_volatility_pct"] else "N/A"
            row = (
                f"{i:<5} {s['ticker']:<15} {s['name']:<28} {s['sector']:<18} "
                f"{s['composite_score']:>9.1f} {s['technical_score']:>6.1f} "
                f"{s['fundamental_score']:>6.1f} {s['trend']:<10} {vol_str:>10}"
            )
            lines.append(row)
        lines.append("")

        # ---- KPI Reference Table ----
        lines.append("KEY FUNDAMENTAL KPIs (Top 10)")
        lines.append("-" * 80)
        kpi_header = f"{'Ticker':<15} {'P/E':>7} {'ROE%':>7} {'RevGrw%':>8} {'Margin%':>8} {'DivYld%':>8} {'D/E':>6} {'Grade':<6}"
        lines.append(kpi_header)
        lines.append("-" * len(kpi_header))
        for s in top10:
            fd = s["fundamental_details"]
            lines.append(
                f"{s['ticker']:<15} "
                f"{str(round(fd.get('pe_ratio', 0) or 0, 1)):>7} "
                f"{str(round(fd.get('roe_pct', 0) or 0, 1)):>7} "
                f"{str(round(fd.get('revenue_growth_pct', 0) or 0, 1)):>8} "
                f"{str(round(fd.get('profit_margin_pct', 0) or 0, 1)):>8} "
                f"{str(round(fd.get('dividend_yield_pct', 0) or 0, 1)):>8} "
                f"{str(round(fd.get('debt_to_equity', 0) or 0, 2)):>6} "
                f"{s['fundamental_grade']:<6}"
            )
        lines.append("")

        # ---- Section 2: AI Deep Analysis ----
        lines.append("=" * 80)
        lines.append("SECTION 2: AI DEEP ANALYSIS — CLAUDE claude-opus-4-7")
        lines.append("=" * 80)
        lines.append("")
        lines.append(ai_analysis)
        lines.append("")

        # ---- Section 3: Timeframe Summary ----
        lines.append("=" * 80)
        lines.append("SECTION 3: INVESTMENT TIMEFRAME SUMMARY")
        lines.append("(Short-Term: 1-3mo | Medium-Term: 3-12mo | Long-Term: 1-3yr)")
        lines.append("=" * 80)
        lines.append("")
        lines.append(timeframe_table)
        lines.append("")

        # ---- Disclaimer ----
        lines.append("=" * 80)
        lines.append("DISCLAIMER")
        lines.append("-" * 80)
        lines.append(
            "This report is generated by an AI system for informational and educational purposes only. "
            "It does NOT constitute financial advice, investment recommendations, or an offer to buy or sell securities. "
            "Investing in stocks involves significant risk, including possible loss of principal. "
            "Past performance is not indicative of future results. "
            "Always conduct your own due diligence and consult a licensed financial advisor before making investment decisions. "
            "Nigeria stock market data sourced via Yahoo Finance and may be subject to delays or inaccuracies."
        )
        lines.append("=" * 80)

        return "\n".join(lines)

    def run(self) -> str:
        print("\n" + "=" * 80)
        print(" NIGERIA STOCK MARKET AI ANALYSIS AGENT")
        print(" Powered by Claude claude-opus-4-7 | NGX Securities")
        print("=" * 80)

        all_results = self.run_screening()

        if not all_results:
            print("ERROR: Could not retrieve data for any NGX stocks.")
            sys.exit(1)

        top10 = all_results[:10]
        print(f"\n[Screening Complete] {len(all_results)} stocks analyzed. Top 10 selected.")

        ai_analysis = self.generate_ai_analysis(top10)
        timeframe_table = self.generate_timeframe_summary(top10)

        report = self._compile_report(all_results, ai_analysis, timeframe_table)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"nigeria_stock_report_{timestamp}.txt"
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"\n[Done] Report saved to: {filepath}")
        return filepath


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    agent = NigeriaStockAgent()
    report_path = agent.run()
    print(f"\nReport path: {report_path}")
