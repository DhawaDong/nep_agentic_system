import logging
from flask import Flask, render_template, request, jsonify

from config import Config
from utils.db import init_db, save_run, get_recent_runs
from agents.orchestrator import Orchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = Flask(__name__)
app.config.from_object(Config)

init_db()
orchestrator = Orchestrator()


@app.route("/")
def index():
    recent = get_recent_runs(10)
    return render_template("index.html", recent=recent)


@app.route("/analyze", methods=["POST"])
def analyze():
    target = request.form.get("target", "").strip().upper()
    if not target:
        return render_template("index.html", error="Please enter a NEPSE symbol.",
                                recent=get_recent_runs(10))

    result = orchestrator.run(target=target)
    run_id = save_run(target=target, market="NEPSE", result=result)
    return render_template("result.html", result=result, run_id=run_id)


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """JSON API: POST {"target": "NABIL"}"""
    payload = request.get_json(silent=True) or {}
    target = (payload.get("target") or "").strip().upper()
    if not target:
        return jsonify({"ok": False, "error": "target is required"}), 400

    result = orchestrator.run(target=target)
    run_id = save_run(target=target, market="NEPSE", result=result)
    return jsonify({"ok": True, "run_id": run_id, "result": result})


@app.route("/history")
def history():
    return jsonify(get_recent_runs(50))


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
