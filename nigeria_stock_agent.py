"""
Nigeria Stock Market Analysis Agent v2
Uses Claude claude-opus-4-7 as primary data + analysis engine for NGX stocks.
Yahoo Finance does not provide NGX data reliably; Claude's training knowledge
covers all major NGX-listed companies with sufficient depth for analysis.
"""

import os
import sys
import json
import re
import warnings
from datetime import datetime
from typing import Dict, List

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

DATA_SCHEMA = {
    "ticker": "NGX ticker string",
    "name": "company name",
    "sector": "sector",
    "price_ngn": "recent share price in NGN",
    "market_cap_bn_ngn": "market cap in billions NGN",
    "pe_ratio": "trailing P/E (null if loss-making)",
    "pb_ratio": "price-to-book ratio",
    "roe_pct": "return on equity as % e.g. 28.5",
    "revenue_growth_pct": "revenue growth YoY as %",
    "profit_margin_pct": "net profit margin as %",
    "dividend_yield_pct": "dividend yield as % or null",
    "debt_to_equity": "D/E ratio (banks typically high)",
    "eps_ngn": "earnings per share in NGN",
    "price_change_1m_pct": "1-month price change %",
    "price_change_3m_pct": "3-month price change %",
    "price_change_6m_pct": "6-month price change %",
    "price_change_1y_pct": "12-month price change %",
    "annual_volatility_pct": "annualised price volatility %",
    "rsi_14": "RSI(14) estimate 0-100",
    "trend": "BULLISH | NEUTRAL | BEARISH",
    "technical_outlook": "BULLISH | NEUTRAL | BEARISH",
    "fundamental_outlook": "STRONG | MODERATE | WEAK",
    "data_confidence_pct": "0-100 confidence in accuracy",
}


# ---------------------------------------------------------------------------
# Scoring engine (Claude-data driven)
# ---------------------------------------------------------------------------

def _technical_score(stock: Dict) -> Dict:
    rsi = stock.get("rsi_14") or 50
    if 40 <= rsi <= 60:
        rsi_score = 80
    elif 30 <= rsi < 40 or 60 < rsi <= 70:
        rsi_score = 60
    elif rsi < 30:
        rsi_score = 90
    else:
        rsi_score = 20

    trend = stock.get("trend", "NEUTRAL")
    trend_score = {"BULLISH": 80, "NEUTRAL": 50, "BEARISH": 20}.get(trend, 50)

    r1 = stock.get("price_change_1m_pct") or 0
    r3 = stock.get("price_change_3m_pct") or 0
    r6 = stock.get("price_change_6m_pct") or 0
    mom_score = max(0, min(50 + r1 * 1.5 + r3 * 0.8 + r6 * 0.5, 100))

    outlook = stock.get("technical_outlook", "NEUTRAL")
    outlook_score = {"BULLISH": 80, "NEUTRAL": 50, "BEARISH": 20}.get(outlook, 50)

    conf_score = min(stock.get("data_confidence_pct") or 70, 100)

    total = (
        rsi_score * 0.15
        + trend_score * 0.25
        + mom_score * 0.25
        + outlook_score * 0.20
        + conf_score * 0.15
    )

    return {
        "score": round(total, 2),
        "trend": trend,
        "current_price": stock.get("price_ngn") or 0,
        "signals": {
            "rsi": rsi,
            "return_1m": r1,
            "return_3m": r3,
            "return_6m": r6,
        },
    }


def _fundamental_score(stock: Dict) -> Dict:
    score = 50.0
    details = {}

    pe = stock.get("pe_ratio")
    if pe and pe > 0:
        if 3 <= pe <= 15:
            score += 15
        elif 15 < pe <= 25:
            score += 8
        elif pe < 3:
            score += 3
        else:
            score -= 5
        details["pe_ratio"] = round(pe, 2)

    roe = stock.get("roe_pct")
    if roe is not None:
        score += 15 if roe >= 20 else 8 if roe >= 10 else 2 if roe >= 0 else -8
        details["roe_pct"] = round(roe, 2)

    rg = stock.get("revenue_growth_pct")
    if rg is not None:
        score += 10 if rg >= 20 else 6 if rg >= 10 else 2 if rg >= 0 else -5
        details["revenue_growth_pct"] = round(rg, 2)

    mg = stock.get("profit_margin_pct")
    if mg is not None:
        score += 10 if mg >= 20 else 5 if mg >= 10 else 1 if mg >= 0 else -8
        details["profit_margin_pct"] = round(mg, 2)

    dy = stock.get("dividend_yield_pct")
    if dy:
        score += 8 if dy >= 5 else 5 if dy >= 2 else 0
        details["dividend_yield_pct"] = round(dy, 2)

    de = stock.get("debt_to_equity")
    if de is not None:
        score += 8 if de < 0.5 else 3 if de < 1.5 else -8 if de > 3 else 0
        details["debt_to_equity"] = round(de, 2)

    fo = (stock.get("fundamental_outlook") or "").upper()
    if "STRONG" in fo:
        score += 5
    elif "WEAK" in fo:
        score -= 5

    score = max(0, min(score, 100))
    grade = "A" if score >= 75 else "B" if score >= 60 else "C" if score >= 45 else "D"
    return {"score": round(score, 2), "grade": grade, "details": details}


def _parse_json_response(text: str) -> list:
    """Robustly extract a JSON list or {stocks:[...]} object from Claude's reply."""
    text = re.sub(r"```(?:json)?\n?", "", text).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        return parsed.get("stocks", parsed.get("data", []))
    except json.JSONDecodeError:
        for pattern in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
            m = re.search(pattern, text)
            if m:
                try:
                    parsed = json.loads(m.group())
                    if isinstance(parsed, list):
                        return parsed
                    return parsed.get("stocks", [])
                except json.JSONDecodeError:
                    continue
    return []


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class NigeriaStockAgent:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-opus-4-7"

    # ---- Phase 1 ----

    def collect_market_data(self) -> list:
        print("\n[Phase 1] Collecting NGX Market Data via Claude Knowledge Base...")
        print("=" * 60)

        stock_list = json.dumps(
            [{"ticker": t, "name": m["name"], "sector": m["sector"]} for t, m in NGX_STOCKS.items()],
            indent=2,
        )

        prompt = f"""You are a Nigerian capital markets data expert (today: {datetime.now().strftime('%B %d, %Y')}).

For each NGX stock below, provide the most recent known financial metrics from your training data.

STOCKS:
{stock_list}

Return ONLY a valid JSON array (no markdown, no prose). Each element must match:
{json.dumps(DATA_SCHEMA, indent=2)}

Rules:
- Start your response with [ and end with ]
- Use null for genuinely unknown fields
- For banks, D/E ratios are naturally high (8-15x) due to leverage — do not penalise
- price_change fields should reflect actual historical NGX price movements you know about
- data_confidence_pct: be honest — 60-75 for estimates, 80+ for well-known figures

["""

        print("Requesting stock data from Claude...", flush=True)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )

        raw = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw = block.text
                break

        # The prompt ends with "[" so prepend it for valid JSON
        raw = "[" + raw if not raw.lstrip().startswith("[") else raw
        stocks = _parse_json_response(raw)
        print(f"Received data for {len(stocks)} stocks.")
        return stocks

    # ---- Phase 2 ----

    def score_and_rank(self, stocks_data: list) -> List[Dict]:
        print("\n[Phase 2] Scoring and Ranking...")
        print("=" * 60)

        results = []
        for stock in stocks_data:
            tech = _technical_score(stock)
            fund = _fundamental_score(stock)
            composite = round(tech["score"] * 0.55 + fund["score"] * 0.45, 2)
            name = stock.get("name", stock.get("ticker", ""))
            print(
                f"  {name:<30} Score={composite:.1f} | "
                f"Tech={tech['score']:.1f} | Fund={fund['score']:.1f} | {tech['trend']}"
            )
            results.append(
                {
                    "ticker": stock.get("ticker", ""),
                    "name": name,
                    "sector": stock.get("sector", ""),
                    "composite_score": composite,
                    "technical_score": tech["score"],
                    "fundamental_score": fund["score"],
                    "trend": tech["trend"],
                    "current_price": tech["current_price"],
                    "signals": tech["signals"],
                    "fundamental_grade": fund["grade"],
                    "fundamental_details": fund["details"],
                    "annual_volatility_pct": stock.get("annual_volatility_pct"),
                    "price_change_1y_pct": stock.get("price_change_1y_pct"),
                    "data_confidence": stock.get("data_confidence_pct", 70),
                    "raw": stock,
                }
            )

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return results

    # ---- Phase 3 ----

    def generate_ai_analysis(self, top_stocks: List[Dict]) -> str:
        print("\n[Phase 3] Claude Deep Analysis (streaming)...")
        print("=" * 60)

        stock_summary = json.dumps(
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
                    "price_change_1y_pct": s["price_change_1y_pct"],
                    "data_confidence_pct": s["data_confidence"],
                    "key_metrics": s["fundamental_details"],
                    "signals": s["signals"],
                }
                for i, s in enumerate(top_stocks)
            ],
            indent=2,
        )

        prompt = f"""You are a senior Nigerian capital markets analyst with 20 years of NGX experience.
Today: {datetime.now().strftime('%B %d, %Y')}.

These are the top 10 NGX stocks from quantitative screening (55% technical / 45% fundamental):

{stock_summary}

Perform a COMPREHENSIVE deep-dive for each stock. For every stock:

1. **Executive Summary** — 3-4 sentences on why it ranked top 10.
2. **Technical Analysis** — Interpret the trend, momentum, RSI, and key price levels.
3. **Fundamental Analysis** — Evaluate PE, ROE, revenue growth, margins, dividends vs sector peers.
4. **Nigeria Macro Context** — CBN monetary policy, naira FX dynamics, oil prices, sector-specific regulations.
5. **Catalysts & Tailwinds** — 3-4 specific near-term catalysts.
6. **Risk Assessment** — Top 3 risks with probability (Low/Medium/High) and severity.
7. **Investment Thesis** — The core bull case in 2-3 sentences.
8. **Confidence Level** — State your overall confidence as %. ONLY recommend if confidence ≥ 85%. Below 85% = "MONITOR ONLY".
9. **12-Month Price Targets** — Bear / Base / Bull case in NGN with rationale.

After all 10 stocks:
- **Portfolio Construction**: Suggested allocation % across the 10 with diversification rationale.
- **NGX Market Outlook 2025–2026**: Overall direction, key investment themes, sector rotation opportunities.

Be specific, cite actual metrics from the data, and deliver institutional-quality analysis."""

        collected = []
        with self.client.messages.stream(
            model=self.model,
            max_tokens=10000,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                collected.append(text)

        print("\n")
        return "".join(collected)

    # ---- Phase 4 ----

    def generate_timeframe_summary(self, top_stocks: List[Dict]) -> str:
        print("\n[Phase 4] Generating Timeframe Investment Summary...")
        print("=" * 60)

        stock_list = "\n".join(
            f"{i+1}. {s['name']} ({s['ticker']}) | Sector: {s['sector']} | "
            f"Score: {s['composite_score']} | Trend: {s['trend']} | "
            f"1Y Return: {s.get('price_change_1y_pct', 'N/A')}% | "
            f"Volatility: {s['annual_volatility_pct']}%"
            for i, s in enumerate(top_stocks)
        )

        prompt = f"""You are a Nigerian capital markets analyst. Today: {datetime.now().strftime('%B %d, %Y')}.

Top 10 NGX stocks:
{stock_list}

For EACH stock provide a structured timeframe investment breakdown:

**SHORT-TERM (1–3 months)**
- Expected return range: X% to Y%
- Primary catalyst: [specific upcoming event or trigger]
- Risk level: Low / Medium / High
- Confidence: XX% (≥ 85% = BUY/HOLD; < 85% = MONITOR ONLY)
- Action: BUY | HOLD | MONITOR ONLY

**MEDIUM-TERM (3–12 months)**
- Expected return range: X% to Y%
- Primary catalyst: [specific growth driver]
- Risk level: Low / Medium / High
- Confidence: XX%
- Action: BUY | HOLD | MONITOR ONLY

**LONG-TERM (1–3 years)**
- Expected return range: X% to Y%
- Primary catalyst: [structural/secular growth story]
- Risk level: Low / Medium / High
- Confidence: XX%
- Action: BUY | HOLD | MONITOR ONLY

---
End with these four sections:
1. **BEST FOR SHORT-TERM** — Top 3 picks with one-line rationale each
2. **BEST FOR MEDIUM-TERM** — Top 3 picks with one-line rationale each
3. **BEST FOR LONG-TERM** — Top 3 picks with one-line rationale each
4. **OVERALL PORTFOLIO RECOMMENDATION** — Ideal blend of timeframe positions for a balanced NGX portfolio

Be honest: flag stocks where macro uncertainty reduces confidence below 85% for any timeframe."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=5000,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )

        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""

    # ---- Report Compiler ----

    def _compile_report(self, all_results: List[Dict], ai_analysis: str, timeframe: str) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        top10 = all_results[:10]

        sector_counts: Dict[str, int] = {}
        for r in all_results:
            sector_counts[r["sector"]] = sector_counts.get(r["sector"], 0) + 1

        lines = [
            "=" * 80,
            "NIGERIA STOCK MARKET — AI-POWERED INVESTMENT ANALYSIS REPORT",
            f"Generated  : {timestamp}",
            f"Model      : Claude claude-opus-4-7  |  NGX Listed Securities",
            f"Data Source: Claude AI Knowledge Base (training data up to early 2025)",
            "=" * 80,
            "",
            "SECTION 1: QUANTITATIVE SCREENING OVERVIEW",
            "-" * 80,
            f"Stocks Screened : {len(all_results)}",
            f"Stocks in Top 10: 10",
            "",
            "Sector Distribution:",
        ]
        for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {sector:<26} {count} stock(s)")
        lines.append("")

        # Top 10 ranking table
        lines.append("TOP 10 COMPOSITE RANKING")
        lines.append("-" * 80)
        hdr = f"{'Rk':<4} {'Ticker':<16} {'Name':<28} {'Sector':<16} {'Score':>7} {'Tech':>6} {'Fund':>6} {'Trend':<10} {'1Y Ret%':>8}"
        lines.append(hdr)
        lines.append("-" * len(hdr))
        for i, s in enumerate(top10, 1):
            ret = f"{s['price_change_1y_pct']:.1f}%" if s.get("price_change_1y_pct") is not None else "N/A"
            lines.append(
                f"{i:<4} {s['ticker']:<16} {s['name']:<28} {s['sector']:<16} "
                f"{s['composite_score']:>7.1f} {s['technical_score']:>6.1f} "
                f"{s['fundamental_score']:>6.1f} {s['trend']:<10} {ret:>8}"
            )
        lines.append("")

        # KPI table
        lines.append("KEY FUNDAMENTAL KPIs")
        lines.append("-" * 80)
        kh = f"{'Ticker':<16} {'Price ₦':>9} {'P/E':>7} {'ROE%':>7} {'RevGrw%':>8} {'Margin%':>8} {'DivYld%':>8} {'Gr':<4}"
        lines.append(kh)
        lines.append("-" * len(kh))
        for s in top10:
            fd = s["fundamental_details"]
            price = f"₦{s['current_price']:.2f}" if s["current_price"] else "N/A"
            lines.append(
                f"{s['ticker']:<16} {price:>9} "
                f"{str(round(fd.get('pe_ratio') or 0, 1)):>7} "
                f"{str(round(fd.get('roe_pct') or 0, 1)):>7} "
                f"{str(round(fd.get('revenue_growth_pct') or 0, 1)):>8} "
                f"{str(round(fd.get('profit_margin_pct') or 0, 1)):>8} "
                f"{str(round(fd.get('dividend_yield_pct') or 0, 1)):>8} "
                f"{s['fundamental_grade']:<4}"
            )
        lines.append("")

        lines += [
            "=" * 80,
            "SECTION 2: AI DEEP ANALYSIS — CLAUDE claude-opus-4-7",
            "=" * 80,
            "",
            ai_analysis,
            "",
            "=" * 80,
            "SECTION 3: INVESTMENT TIMEFRAME ANALYSIS",
            "Short-Term: 1–3 months | Medium-Term: 3–12 months | Long-Term: 1–3 years",
            "=" * 80,
            "",
            timeframe,
            "",
            "=" * 80,
            "DISCLAIMER & DATA NOTICE",
            "-" * 80,
            (
                "This report is generated by an AI system using Claude claude-opus-4-7. "
                "Metrics and price data are sourced from the model's training knowledge and may not reflect "
                "current market prices or the latest financial results. "
                "This is NOT financial advice. Always verify data against official NGX/company sources "
                "and consult a licensed investment adviser before making any investment decision. "
                "Past performance is no guarantee of future results."
            ),
            "=" * 80,
        ]

        return "\n".join(lines)

    # ---- Main Pipeline ----

    def run(self) -> str:
        print("\n" + "=" * 80)
        print(" NIGERIA STOCK MARKET AI ANALYSIS AGENT v2")
        print(" Powered by Claude claude-opus-4-7  |  NGX Securities")
        print("=" * 80)

        stocks_data = self.collect_market_data()
        if not stocks_data:
            print("ERROR: No stock data returned.")
            sys.exit(1)

        all_results = self.score_and_rank(stocks_data)
        top10 = all_results[:10]
        print(f"\n[Screening Complete] {len(all_results)} stocks scored. Top 10 selected.")

        ai_analysis = self.generate_ai_analysis(top10)
        timeframe = self.generate_timeframe_summary(top10)

        report = self._compile_report(all_results, ai_analysis, timeframe)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"nigeria_stock_report_{timestamp}.txt"
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"\n[Done] Report saved to: {filepath}")
        return filepath


if __name__ == "__main__":
    agent = NigeriaStockAgent()
    agent.run()
