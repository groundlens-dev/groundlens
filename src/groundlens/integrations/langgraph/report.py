"""Self-contained HTML report generator for LangGraph agent traces.

Produces a single HTML file with no external dependencies that visualizes:

- Triage summary with step counts by category.
- Timeline of agent execution with color-coded scores.
- SGI vs DGI method indicators per step.
- Expandable details showing input, output, context, and score breakdown.

Example:
    >>> trace = gl.get_trace()
    >>> html = trace.to_html("report.html")
    >>> # Open report.html in any browser
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from groundlens.integrations.langgraph.trace import AgentTrace


def _escape(text: str, max_len: int = 2000) -> str:
    """HTML-escape and optionally truncate text.

    Args:
        text: Raw text to escape.
        max_len: Maximum character length before truncation.

    Returns:
        HTML-safe string, truncated with ellipsis if needed.
    """
    if len(text) > max_len:
        text = text[:max_len] + "…"
    return html.escape(text)


def _triage_color(triage: str) -> str:
    """Map triage category to a CSS color.

    Args:
        triage: One of ``"trusted"``, ``"review"``, or ``"flagged"``.

    Returns:
        Hex color string.
    """
    return {
        "trusted": "#10b981",
        "review": "#f59e0b",
        "flagged": "#ef4444",
    }.get(triage, "#6b7280")


def _triage_icon(triage: str) -> str:
    """Map triage category to a Unicode indicator.

    Args:
        triage: One of ``"trusted"``, ``"review"``, or ``"flagged"``.

    Returns:
        Unicode character for display.
    """
    return {
        "trusted": "✓",
        "review": "⚠",
        "flagged": "✗",
    }.get(triage, "?")


def _method_badge(method: str) -> str:
    """Generate an HTML badge for the scoring method.

    Args:
        method: ``"sgi"`` or ``"dgi"``.

    Returns:
        HTML span element with method-specific styling.
    """
    if method == "sgi":
        return '<span class="badge badge-sgi">SGI · grounded</span>'
    return '<span class="badge badge-dgi">DGI · ungrounded</span>'


def render_html_report(trace: AgentTrace) -> str:
    """Render a complete self-contained HTML triage report.

    Args:
        trace: The AgentTrace to visualize.

    Returns:
        Complete HTML string ready to write to a file.
    """
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build step rows
    step_rows = []
    for step in trace.steps:
        color = _triage_color(step.triage)
        icon = _triage_icon(step.triage)
        badge = _method_badge(step.method)

        context_html = ""
        if step.context:
            context_html = f"""
            <div class="detail-section">
                <div class="detail-label">Context (tool output)</div>
                <pre class="detail-text">{_escape(step.context)}</pre>
            </div>"""

        step_rows.append(f"""
        <div class="step" data-triage="{step.triage}">
            <div class="step-header" onclick="this.parentElement.classList.toggle('expanded')">
                <div class="step-indicator" style="background:{color}">{icon}</div>
                <div class="step-info">
                    <div class="step-title">
                        <span class="node-name">{_escape(step.node_name)}</span>
                        {badge}
                        <span class="step-duration">{step.duration_ms:.0f}ms</span>
                    </div>
                    <div class="step-score">
                        {step.method.upper()}={step.score.value:.3f}
                        · normalized={step.score.normalized:.3f}
                        · <span style="color:{color};font-weight:600">{step.triage}</span>
                    </div>
                </div>
                <div class="expand-icon">▸</div>
            </div>
            <div class="step-details">
                <div class="detail-section">
                    <div class="detail-label">Input (prompt)</div>
                    <pre class="detail-text">{_escape(step.input_text)}</pre>
                </div>
                <div class="detail-section">
                    <div class="detail-label">Output (LLM response)</div>
                    <pre class="detail-text">{_escape(step.output_text)}</pre>
                </div>{context_html}
                <div class="detail-section">
                    <div class="detail-label">Explanation</div>
                    <p class="detail-text explanation">{_escape(step.score.explanation)}</p>
                </div>
            </div>
        </div>""")

    steps_html = "\n".join(step_rows)

    # Compute score bar widths
    total = trace.total_steps or 1
    trusted_pct = (trace.trusted_steps / total) * 100
    review_pct = (trace.review_steps / total) * 100
    flagged_pct = (trace.flagged_steps / total) * 100

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>groundlens Triage Report</title>
<style>
:root {{
    --bg: #0f172a;
    --surface: #1e293b;
    --surface-2: #334155;
    --text: #f1f5f9;
    --text-muted: #94a3b8;
    --border: #475569;
    --trusted: #10b981;
    --review: #f59e0b;
    --flagged: #ef4444;
    --sgi: #3b82f6;
    --dgi: #8b5cf6;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --mono: 'SF Mono', SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 2rem;
    max-width: 960px;
    margin: 0 auto;
}}
.header {{
    margin-bottom: 2rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid var(--border);
}}
.header h1 {{
    font-size: 1.5rem;
    font-weight: 700;
    margin-bottom: 0.25rem;
}}
.header .subtitle {{
    color: var(--text-muted);
    font-size: 0.875rem;
}}
.summary {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
}}
.summary-card {{
    background: var(--surface);
    border-radius: 8px;
    padding: 1rem;
    text-align: center;
}}
.summary-card .count {{
    font-size: 2rem;
    font-weight: 700;
    line-height: 1.2;
}}
.summary-card .label {{
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
}}
.score-bar {{
    display: flex;
    height: 8px;
    border-radius: 4px;
    overflow: hidden;
    margin-bottom: 2rem;
    background: var(--surface);
}}
.score-bar div {{
    transition: width 0.3s ease;
}}
.bar-trusted {{ background: var(--trusted); }}
.bar-review {{ background: var(--review); }}
.bar-flagged {{ background: var(--flagged); }}

.steps-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
}}
.steps-header h2 {{
    font-size: 1.125rem;
    font-weight: 600;
}}
.filter-buttons {{
    display: flex;
    gap: 0.5rem;
}}
.filter-btn {{
    background: var(--surface);
    color: var(--text-muted);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.25rem 0.75rem;
    font-size: 0.75rem;
    cursor: pointer;
    transition: all 0.2s;
}}
.filter-btn:hover,
.filter-btn.active {{
    background: var(--surface-2);
    color: var(--text);
}}

.step {{
    background: var(--surface);
    border-radius: 8px;
    margin-bottom: 0.5rem;
    overflow: hidden;
    border-left: 3px solid transparent;
}}
.step[data-triage="trusted"] {{ border-left-color: var(--trusted); }}
.step[data-triage="review"] {{ border-left-color: var(--review); }}
.step[data-triage="flagged"] {{ border-left-color: var(--flagged); }}

.step-header {{
    display: flex;
    align-items: center;
    padding: 0.75rem 1rem;
    cursor: pointer;
    user-select: none;
    gap: 0.75rem;
}}
.step-header:hover {{
    background: var(--surface-2);
}}
.step-indicator {{
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.875rem;
    flex-shrink: 0;
    color: white;
}}
.step-info {{
    flex: 1;
    min-width: 0;
}}
.step-title {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
}}
.node-name {{
    font-weight: 600;
    font-size: 0.9375rem;
}}
.step-duration {{
    color: var(--text-muted);
    font-size: 0.75rem;
}}
.step-score {{
    font-size: 0.8125rem;
    color: var(--text-muted);
    font-family: var(--mono);
}}
.expand-icon {{
    color: var(--text-muted);
    font-size: 0.875rem;
    transition: transform 0.2s;
}}
.step.expanded .expand-icon {{
    transform: rotate(90deg);
}}
.step-details {{
    display: none;
    padding: 0 1rem 1rem 3.5rem;
}}
.step.expanded .step-details {{
    display: block;
}}
.detail-section {{
    margin-bottom: 1rem;
}}
.detail-label {{
    font-size: 0.6875rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 0.25rem;
}}
.detail-text {{
    background: var(--bg);
    border-radius: 6px;
    padding: 0.75rem;
    font-size: 0.8125rem;
    line-height: 1.5;
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-x: auto;
    font-family: var(--mono);
    max-height: 300px;
    overflow-y: auto;
}}
.explanation {{
    font-family: var(--font);
    font-style: italic;
}}

.badge {{
    font-size: 0.6875rem;
    padding: 0.125rem 0.5rem;
    border-radius: 9999px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}}
.badge-sgi {{
    background: rgba(59, 130, 246, 0.15);
    color: var(--sgi);
}}
.badge-dgi {{
    background: rgba(139, 92, 246, 0.15);
    color: var(--dgi);
}}

.footer {{
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
    font-size: 0.75rem;
    color: var(--text-muted);
    display: flex;
    justify-content: space-between;
}}
.footer a {{
    color: var(--sgi);
    text-decoration: none;
}}
.footer a:hover {{
    text-decoration: underline;
}}
</style>
</head>
<body>

<div class="header">
    <h1>groundlens Triage Report</h1>
    <div class="subtitle">Generated {now} · {trace.total_steps} steps evaluated</div>
</div>

<div class="summary">
    <div class="summary-card">
        <div class="count">{trace.total_steps}</div>
        <div class="label">Total Steps</div>
    </div>
    <div class="summary-card">
        <div class="count" style="color:var(--trusted)">{trace.trusted_steps}</div>
        <div class="label">Trusted</div>
    </div>
    <div class="summary-card">
        <div class="count" style="color:var(--review)">{trace.review_steps}</div>
        <div class="label">Review</div>
    </div>
    <div class="summary-card">
        <div class="count" style="color:var(--flagged)">{trace.flagged_steps}</div>
        <div class="label">Flagged</div>
    </div>
    <div class="summary-card">
        <div class="count">{trace.total_duration_ms:.0f}
        <span style="font-size:0.875rem">ms</span></div>
        <div class="label">Total Time</div>
    </div>
</div>

<div class="score-bar">
    <div class="bar-trusted" style="width:{trusted_pct:.1f}%"></div>
    <div class="bar-review" style="width:{review_pct:.1f}%"></div>
    <div class="bar-flagged" style="width:{flagged_pct:.1f}%"></div>
</div>

<div class="steps-header">
    <h2>Execution Timeline</h2>
    <div class="filter-buttons">
        <button class="filter-btn active" onclick="filterSteps('all')">All</button>
        <button class="filter-btn" onclick="filterSteps('flagged')">Flagged</button>
        <button class="filter-btn" onclick="filterSteps('review')">Review</button>
        <button class="filter-btn" onclick="filterSteps('trusted')">Trusted</button>
    </div>
</div>

<div class="steps-container">
{steps_html}
</div>

<div class="footer">
    <span>groundlens v2026.5 · Geometric hallucination triage</span>
    <a href="https://groundlens.dev" target="_blank">groundlens.dev</a>
</div>

<script>
function filterSteps(triage) {{
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    document.querySelectorAll('.step').forEach(s => {{
        if (triage === 'all' || s.dataset.triage === triage) {{
            s.style.display = '';
        }} else {{
            s.style.display = 'none';
        }}
    }});
}}
</script>

</body>
</html>"""
