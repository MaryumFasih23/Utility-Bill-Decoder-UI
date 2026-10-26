"""Custom CSS & theme styling for the Utility Bill Decoder Streamlit application."""

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --bg-dark: #090D16;
    --card-bg: rgba(17, 24, 39, 0.75);
    --card-border: rgba(255, 255, 255, 0.08);
    --accent-emerald: #10B981;
    --accent-cyan: #06B6D4;
    --accent-blue: #3B82F6;
    --accent-amber: #F59E0B;
    --accent-rose: #F43F5E;
    --text-primary: #F9FAFB;
    --text-secondary: #9CA3AF;
    --text-muted: #6B7280;
}

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
}

code, pre, .stCode, [data-testid="stMarkdownContainer"] pre {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Main Container Adjustments */
.main .block-container {
    padding-top: 1.8rem;
    padding-bottom: 3rem;
    max-width: 98% !important;
}

/* Glassmorphism Cards */
.glass-card {
    background: var(--card-bg);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--card-border);
    border-radius: 16px;
    padding: 1.25rem 1.5rem;
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    margin-bottom: 1rem;
    transition: transform 0.2s ease, border-color 0.2s ease;
}

.glass-card:hover {
    border-color: rgba(255, 255, 255, 0.16);
}

/* Header & Banner */
.app-header {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(6, 182, 212, 0.12) 50%, rgba(59, 130, 246, 0.1) 100%);
    border: 1px solid rgba(16, 185, 129, 0.25);
    border-radius: 20px;
    padding: 1.5rem 2rem;
    margin-bottom: 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 1rem;
}

.app-title {
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    background: linear-gradient(135deg, #FFFFFF 30%, #A7F3D0 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
    line-height: 1.2;
}

.app-subtitle {
    font-size: 0.95rem;
    color: var(--text-secondary);
    margin-top: 0.25rem;
    font-weight: 400;
}

/* Badges */
.badge {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.28rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
}

.badge-ke {
    background: rgba(245, 158, 11, 0.18);
    color: #FBBF24;
    border: 1px solid rgba(245, 158, 11, 0.35);
}

.badge-lesco {
    background: rgba(16, 185, 129, 0.18);
    color: #34D399;
    border: 1px solid rgba(16, 185, 129, 0.35);
}

.badge-iesco {
    background: rgba(6, 182, 212, 0.18);
    color: #38BDF8;
    border: 1px solid rgba(6, 182, 212, 0.35);
}

.badge-verified {
    background: rgba(99, 102, 241, 0.18);
    color: #A5B4FC;
    border: 1px solid rgba(99, 102, 241, 0.35);
}

/* Metric Display Cards */
.metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 0.85rem;
    margin-bottom: 1.25rem;
}

.metric-card {
    background: rgba(17, 24, 39, 0.85);
    border: 1px solid var(--card-border);
    border-radius: 14px;
    padding: 1rem 1.15rem;
    position: relative;
    overflow: hidden;
}

.metric-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 4px;
    height: 100%;
    background: var(--accent-emerald);
}

.metric-card.accent-cyan::before { background: var(--accent-cyan); }
.metric-card.accent-amber::before { background: var(--accent-amber); }
.metric-card.accent-blue::before { background: var(--accent-blue); }
.metric-card.accent-rose::before { background: var(--accent-rose); }

.metric-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.35rem;
}

.metric-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.1;
    letter-spacing: -0.02em;
}

.metric-sub {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-top: 0.3rem;
}

/* Q&A Section Styling */
.qa-card {
    background: rgba(17, 24, 39, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 14px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
}

.qa-card.custom-qa {
    border: 1px solid rgba(16, 185, 129, 0.3);
    background: rgba(16, 185, 129, 0.05);
}

.qa-question {
    font-size: 0.98rem;
    font-weight: 600;
    color: #F3F4F6;
    margin-bottom: 0.5rem;
}

.qa-answer {
    font-size: 0.92rem;
    color: #D1D5DB;
    line-height: 1.55;
    background: rgba(0, 0, 0, 0.25);
    padding: 0.75rem 1rem;
    border-radius: 8px;
    border-left: 3px solid var(--accent-emerald);
}

.provenance-tag {
    display: inline-block;
    font-size: 0.72rem;
    font-family: 'JetBrains Mono', monospace;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #9CA3AF;
    padding: 0.15rem 0.45rem;
    border-radius: 4px;
    margin-right: 0.35rem;
    margin-top: 0.35rem;
}

/* Image preview container */
.bill-image-frame {
    border: 1px solid var(--card-border);
    border-radius: 14px;
    overflow: hidden;
    background: #0D1117;
    padding: 0.5rem;
    text-align: center;
}

/* Tab tweaks */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background-color: transparent;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 10px;
    padding: 8px 18px;
    font-weight: 600;
    font-size: 0.88rem;
    border: 1px solid transparent;
}

.stTabs [aria-selected="true"] {
    background-color: rgba(16, 185, 129, 0.15) !important;
    border: 1px solid rgba(16, 185, 129, 0.35) !important;
    color: #34D399 !important;
}

/* Button overrides */
.stButton > button {
    border-radius: 10px;
    font-weight: 600;
    transition: all 0.2s ease;
}

.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
}
</style>
"""

def provider_badge(provider: str) -> str:
    p = (provider or '').upper()
    cls = 'badge-ke' if 'KE' in p else 'badge-lesco' if 'LESCO' in p else 'badge-iesco'
    return f'<span class="badge {cls}">⚡ {provider or "Unknown"}</span>'

def status_badge(text: str, color_class: str = "badge-verified") -> str:
    return f'<span class="badge {color_class}">{text}</span>'
