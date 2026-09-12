"""Final Agent: synthesizes every upstream agent's output into one
plain-English explanation using the heavier Groq model."""
import json
from config import Config
from utils.groq_client import chat


class FinalAgent:
    def explain(self, context: dict) -> dict:
        system = (
            "You are the lead analyst on a multi-agent market analysis system. "
            "You receive structured outputs from data, technical, sentiment, "
            "sector, correlation, forecasting, and risk agents. Synthesize them "
            "into a clear, well-organized explanation for a retail investor. "
            "Use short headed sections. Be direct about uncertainty - this is "
            "not financial advice and you should say so once, briefly, at the end. "
            "Do not invent numbers that are not present in the provided context."
        )
        user = (
            "Here is the full agent output context (JSON):\n\n"
            f"{json.dumps(context, default=str, indent=2)[:6000]}\n\n"
            "Write the final report with these sections: Summary, Technical Read, "
            "Sentiment & News, Forecast, Risk Assessment, Bottom Line."
        )
        text = chat(system, user, model=Config.GROQ_MODEL_HEAVY, temperature=0.4, max_tokens=1200)
        return {"ok": True, "report": text}
