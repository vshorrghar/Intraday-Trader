"""HTML report builder using Jinja2 templates.

Renders morning brief, midday snapshot, and end-of-day report HTML
from context dictionaries containing portfolio data and market information.
"""

from __future__ import annotations

import logging
import os

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=True,
)


def build_morning_brief(context: dict) -> str:
    """Render morning brief HTML from context.

    Expected context keys: report_date, portfolio_summary, indices, fii_dii, news
    """
    template = _env.get_template("morning_brief.html")
    return template.render(**context)


def build_midday_snapshot(context: dict) -> str:
    """Render midday snapshot HTML from context.

    Expected context keys: report_date, intraday_setups, portfolio_summary, deals
    """
    template = _env.get_template("midday_snapshot.html")
    return template.render(**context)


def build_eod_report(context: dict) -> str:
    """Render end-of-day report HTML from context.

    Expected context keys: report_date, portfolio_summary, verdicts,
    mf_recommendations, tax_harvest_candidates, ipo_data, fii_dii
    """
    template = _env.get_template("eod_report.html")
    return template.render(**context)
