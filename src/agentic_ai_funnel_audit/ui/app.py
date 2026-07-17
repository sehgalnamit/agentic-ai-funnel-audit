import os
import sys
import uuid
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

# Make the package importable when running from the repo root
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agentic_ai_funnel_audit.storage import AuditStore

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")
store = AuditStore()


@app.route("/")
def index():
    return redirect(url_for("intake"))


@app.route("/intake", methods=["GET", "POST"])
def intake():
    if request.method == "POST":
        idea_id = request.form.get("idea_id") or str(uuid.uuid4())
        payload = {
            "title": request.form.get("title"),
            "description": request.form.get("description"),
            "owner": request.form.get("owner"),
            "estimated_benefit": request.form.get("estimated_benefit"),
            "risk_level": request.form.get("risk_level"),
        }
        entry = store.save(idea_id, payload)
        flash(f"Saved intake: {entry.idea_id}")
        return redirect(url_for("dashboard"))
    return render_template("intake.html")


@app.route("/dashboard")
def dashboard():
    entries = store.list()
    return render_template("dashboard.html", entries=entries)


@app.route("/entry/<idea_id>", methods=["GET"])
def entry_detail(idea_id):
    entry = store.get(idea_id)
    if not entry:
        flash("Entry not found", "danger")
        return redirect(url_for("dashboard"))
    return render_template("detail.html", entry=entry)


@app.route("/entry/<idea_id>/override", methods=["POST"])
def entry_override(idea_id):
    action = request.form.get("action")
    comment = request.form.get("comment")
    override_payload = {"action": action, "comment": comment, "by": request.form.get("user")}
    entry = store.override(idea_id, override_payload)
    if not entry:
        flash("Failed to override: entry not found", "danger")
    else:
        flash(f"Set override for {idea_id}: {action}")
    return redirect(url_for("entry_detail", idea_id=idea_id))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
