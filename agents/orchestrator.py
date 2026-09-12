"""
Orchestrator: mirrors the diagram, scoped entirely to NEPSE.

    Data Agents (NEPSE market/security/sector-peers, Macro)
    Event Agents (News/Political/Economic/Company)
        -> Analysis Agents (Technical/Sector/Sentiment/Correlation)
        -> Forecasting Agent (XGBoost)
        -> Risk Agent
        -> Final Agent (Groq LLM synthesis)

Data/event agents run concurrently (they're independent I/O calls), then
their outputs feed the analysis stage, then forecasting, then risk, then
the final LLM synthesis.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from agents.data_agents import NepseAgent, MacroAgent
from agents.event_agents import NewsAgent, PoliticalAgent, EconomicAgent, CompanyAgent
from agents.analysis_agents import TechnicalAgent, CorrelationAgent, SectorAgent, SentimentAgent
from agents.forecasting_agent import ForecastingAgent
from agents.risk_agent import RiskAgent
from agents.final_agent import FinalAgent

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self):
        self.nepse_agent = NepseAgent()
        self.macro_agent = MacroAgent()

        self.news_agent = NewsAgent()
        self.political_agent = PoliticalAgent()
        self.economic_agent = EconomicAgent()
        self.company_agent = CompanyAgent()

        self.technical_agent = TechnicalAgent()
        self.correlation_agent = CorrelationAgent()
        self.sector_agent = SectorAgent()
        self.sentiment_agent = SentimentAgent()

        self.forecasting_agent = ForecastingAgent()
        self.risk_agent = RiskAgent()
        self.final_agent = FinalAgent()

    def run(self, target: str) -> dict:
        """target: a NEPSE symbol, e.g. 'NABIL', 'NHPC', 'HIDCL'."""
        target = target.upper()

        # ---- 1. Data agents (sequential where one depends on another) ----
        security = self.nepse_agent.get_security(target)
        market_status = self.nepse_agent.get_market_status()
        breadth = self.nepse_agent.get_market_breadth()
        sector_peers = self.nepse_agent.get_sector_peers(target) if security.get("ok") else \
            {"ok": False, "error": "No security data to derive sector peers from"}
        price_history = self.nepse_agent.get_price_history(target)
        closes = price_history.get("close", []) if price_history.get("ok") else []

        company_name = security.get("name", target) if security.get("ok") else target

        # ---- 2. Event agents run concurrently (independent I/O) ----
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {
                "macro": pool.submit(self.macro_agent.get_country_macro, "NP"),
                "news": pool.submit(self.news_agent.get, company_name),
                "company_news": pool.submit(self.company_agent.get, company_name),
                "political": pool.submit(self.political_agent.get),
                "economic": pool.submit(self.economic_agent.get),
            }
            results = {}
            for key, fut in futures.items():
                try:
                    results[key] = fut.result(timeout=25)
                except Exception as e:
                    logger.exception("Agent %s failed", key)
                    results[key] = {"ok": False, "error": str(e)}

        # ---- 3. Analysis agents ----
        technical = self.technical_agent.analyze(closes)

        peer_closes_by_symbol = {}
        if sector_peers.get("ok") and closes:
            for peer in sector_peers.get("peers", [])[:5]:
                peer_hist = self.nepse_agent.get_price_history(peer["symbol"])
                if peer_hist.get("ok"):
                    peer_closes_by_symbol[peer["symbol"]] = peer_hist["close"]
        correlation = self.correlation_agent.analyze(closes, peer_closes_by_symbol)

        sector_ctx = self.sector_agent.analyze(
            sector=sector_peers.get("sector") if sector_peers.get("ok") else security.get("sector"),
            company_name=company_name,
            peer_avg_change=sector_peers.get("peer_avg_percent_change") if sector_peers.get("ok") else None,
            peers=sector_peers.get("peers") if sector_peers.get("ok") else [],
        ) if security.get("ok") else {"ok": False, "error": "No security data for sector analysis"}

        all_headlines = (
            (results["news"].get("items", []) if results["news"].get("ok") else []) +
            (results["company_news"].get("items", []) if results["company_news"].get("ok") else [])
        )
        sentiment = self.sentiment_agent.analyze(company_name, all_headlines)

        # ---- 4. Forecasting ----
        forecast = self.forecasting_agent.forecast(closes, horizon=5) if closes else {"ok": False, "error": "No price history"}

        # ---- 5. Risk ----
        risk = self.risk_agent.analyze(closes, forecast, sentiment) if closes else {"ok": False, "error": "No price history"}

        # ---- 6. Final synthesis ----
        context = {
            "target": target,
            "market": "NEPSE",
            "security": {k: v for k, v in security.items() if k != "ok"} if security.get("ok") else security,
            "market_status": market_status,
            "market_breadth": breadth,
            "macro": results["macro"],
            "technical": technical,
            "correlation": correlation,
            "sector": sector_ctx,
            "sentiment": sentiment,
            "forecast": forecast,
            "risk": risk,
            "political_headlines": results["political"],
            "economic_headlines": results["economic"],
        }
        final = self.final_agent.explain(context)

        return {
            "target": target,
            "market": "NEPSE",
            "raw": {
                "security": security,
                "market_status": market_status,
                "market_breadth": breadth,
                "sector_peers": sector_peers,
                "macro": results["macro"],
                "news": results["news"],
                "company_news": results["company_news"],
                "political": results["political"],
                "economic": results["economic"],
            },
            "analysis": {
                "technical": technical,
                "correlation": correlation,
                "sector": sector_ctx,
                "sentiment": sentiment,
            },
            "forecast": forecast,
            "risk": risk,
            "final_report": final.get("report"),
        }
