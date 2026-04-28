"""Static dashboard builder for Nginx serving.

Generates HTML/CSS/JS files containing portfolio summary, stock verdicts,
MF recommendations, and FII/DII flow visualization. Responsive design
for desktop and mobile.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def build_dashboard(context: dict, output_dir: str) -> None:
    """Generate static dashboard files for Nginx serving.

    Args:
        context: Dictionary with keys: portfolio_summary, verdicts,
                 mf_recommendations, fii_dii, report_date
        output_dir: Directory to write dashboard files to.
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "api"), exist_ok=True)

    portfolio = context.get("portfolio_summary", {})
    verdicts = context.get("verdicts", [])
    mf_recs = context.get("mf_recommendations", [])
    fii_dii = context.get("fii_dii", None)
    report_date = context.get("report_date", datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"))

    # Write JSON data for API endpoint
    api_data = {
        "portfolio_summary": _serialize(portfolio),
        "verdicts": [_serialize(v) for v in verdicts],
        "mf_recommendations": [_serialize(r) for r in mf_recs],
        "fii_dii": _serialize(fii_dii) if fii_dii else None,
        "updated_at": report_date,
    }
    with open(os.path.join(output_dir, "api", "latest.json"), "w") as f:
        json.dump(api_data, f, indent=2, default=str)

    html = _render_dashboard_html(portfolio, verdicts, mf_recs, fii_dii, report_date)
    with open(os.path.join(output_dir, "index.html"), "w") as f:
        f.write(html)

    logger.info("Dashboard generated at %s", output_dir)


def _serialize(obj) -> dict | None:
    """Convert dataclass or dict to a plain dict."""
    if obj is None:
        return None
    if hasattr(obj, "__dict__") and not isinstance(obj, dict):
        return {k: str(v) if isinstance(v, datetime) else v for k, v in obj.__dict__.items()}
    if isinstance(obj, dict):
        return obj
    return str(obj)


def _render_dashboard_html(portfolio, verdicts, mf_recs, fii_dii, report_date) -> str:
    """Render the full dashboard HTML string."""
    invested = _get(portfolio, "total_invested", 0)
    current = _get(portfolio, "current_value", 0)
    pnl = _get(portfolio, "total_pnl", 0)
    pnl_class = "positive" if pnl >= 0 else "negative"

    verdict_rows = ""
    for v in verdicts:
        name = _get(v, "name", "")
        verdict = _get(v, "verdict", "")
        target = _get(v, "target_price", 0)
        sl = _get(v, "stop_loss", 0)
        tax = _get(v, "tax_harvest_flag", False)
        tax_badge = '<span class="tax-flag">TLH</span>' if tax else ""
        verdict_rows += f"""<tr>
            <td>{name}</td>
            <td><span class="verdict-pill verdict-{verdict}">{verdict.upper()}</span></td>
            <td>₹{target:.2f}</td><td>₹{sl:.2f}</td><td>{tax_badge}</td></tr>\n"""

    mf_rows = ""
    for r in mf_recs:
        sname = _get(r, "scheme_name", "")
        rec = _get(r, "recommendation", "")
        alt = _get(r, "alternative_scheme", "-") or "-"
        mf_rows += f'<tr><td>{sname}</td><td class="rec-{rec}">{rec.upper()}</td><td>{alt}</td></tr>\n'

    fii_section = ""
    if fii_dii:
        fii_net = _get(fii_dii, "fii_net", 0)
        dii_net = _get(fii_dii, "dii_net", 0)
        fii_cls = "positive" if fii_net >= 0 else "negative"
        dii_cls = "positive" if dii_net >= 0 else "negative"
        fii_section = f"""<div class="card"><h2>FII / DII Flows</h2>
            <div class="bar-row"><span class="bar-label">FII</span>
            <div class="bar bar-fii" style="width:{min(abs(fii_net)/100,200)}px"></div>
            <span class="{fii_cls}">{fii_net:+.0f} Cr</span></div>
            <div class="bar-row"><span class="bar-label">DII</span>
            <div class="bar bar-dii" style="width:{min(abs(dii_net)/100,200)}px"></div>
            <span class="{dii_cls}">{dii_net:+.0f} Cr</span></div></div>"""
    else:
        fii_section = '<div class="card"><h2>FII / DII Flows</h2><p class="neutral">Data unavailable</p></div>'

    return _DASHBOARD_TEMPLATE.format(
        report_date=report_date,
        invested=f"{invested:,.0f}",
        current=f"{current:,.0f}",
        pnl=f"{pnl:,.0f}",
        pnl_class=pnl_class,
        verdict_rows=verdict_rows or '<tr><td colspan="5" class="neutral">No verdicts</td></tr>',
        mf_rows=mf_rows or '<tr><td colspan="3" class="neutral">No recommendations</td></tr>',
        fii_section=fii_section,
    )


def _get(obj, key, default=None):
    """Get attribute from dict or dataclass."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


_DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Wealth Builder Pro Dashboard</title>
<style>
body {{ margin:0; padding:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f4f6f9; color:#333; }}
.header {{ background:#1a1a2e; color:#fff; padding:20px; text-align:center; }}
.header h1 {{ margin:0; font-size:24px; }}
.header .date {{ font-size:13px; color:#a0a0c0; margin-top:4px; }}
.container {{ max-width:900px; margin:0 auto; padding:16px; }}
.card {{ background:#fff; border-radius:8px; padding:16px; margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,0.08); }}
.card h2 {{ margin:0 0 12px; font-size:16px; color:#1a1a2e; border-bottom:2px solid #e8e8f0; padding-bottom:8px; }}
.summary-grid {{ display:flex; flex-wrap:wrap; gap:12px; }}
.summary-item {{ flex:1; min-width:140px; text-align:center; padding:14px; background:#f8f9fc; border-radius:6px; }}
.summary-item .label {{ font-size:11px; color:#666; text-transform:uppercase; }}
.summary-item .value {{ font-size:22px; font-weight:700; margin-top:4px; }}
.positive {{ color:#16a34a; }} .negative {{ color:#dc2626; }} .neutral {{ color:#6b7280; }}
.verdict-pill {{ display:inline-block; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; color:#fff; }}
.verdict-buy {{ background:#16a34a; }} .verdict-hold {{ background:#f59e0b; }}
.verdict-sell {{ background:#dc2626; }} .verdict-exit {{ background:#7c3aed; }}
.rec-continue {{ color:#16a34a; font-weight:600; }} .rec-stop {{ color:#dc2626; font-weight:600; }}
.rec-switch {{ color:#f59e0b; font-weight:600; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ text-align:left; padding:8px; background:#f1f5f9; color:#475569; font-size:11px; text-transform:uppercase; }}
td {{ padding:8px; border-bottom:1px solid #e8e8f0; }}
.tax-flag {{ background:#fef3c7; color:#92400e; padding:2px 6px; border-radius:4px; font-size:11px; }}
.bar-row {{ display:flex; align-items:center; gap:8px; margin:6px 0; }}
.bar-label {{ width:40px; font-size:12px; font-weight:600; }}
.bar {{ height:18px; border-radius:4px; min-width:2px; }}
.bar-fii {{ background:#3b82f6; }} .bar-dii {{ background:#f59e0b; }}
.footer {{ text-align:center; padding:16px; font-size:11px; color:#999; }}
@media (max-width:600px) {{
  .summary-item {{ min-width:100px; }} .summary-item .value {{ font-size:16px; }}
  table {{ font-size:11px; }} th,td {{ padding:6px 4px; }}
}}
</style>
</head>
<body>
<div class="header"><h1>📊 Wealth Builder Pro</h1><div class="date">{report_date}</div></div>
<div class="container">
<div class="card"><h2>Portfolio Summary</h2>
<div class="summary-grid">
<div class="summary-item"><div class="label">Invested</div><div class="value">₹{invested}</div></div>
<div class="summary-item"><div class="label">Current Value</div><div class="value">₹{current}</div></div>
<div class="summary-item"><div class="label">P&amp;L</div><div class="value {pnl_class}">₹{pnl}</div></div>
</div></div>
<div class="card"><h2>Stock Verdicts</h2>
<table><tr><th>Stock</th><th>Verdict</th><th>Target</th><th>SL</th><th>Tax</th></tr>
{verdict_rows}</table></div>
<div class="card"><h2>MF Recommendations</h2>
<table><tr><th>Scheme</th><th>Action</th><th>Alternative</th></tr>
{mf_rows}</table></div>
{fii_section}
</div>
<div class="footer">Wealth Builder Pro · Updated {report_date}</div>
<script>
fetch('/api/latest').then(r=>r.json()).then(d=>console.log('Dashboard data loaded',d)).catch(()=>{{}});
</script>
</body></html>"""
