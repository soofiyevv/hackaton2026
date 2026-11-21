"""UniResolve AI - Streamlit frontend.

Run from the repository root (so .streamlit/config.toml applies):
    streamlit run frontend/app.py
"""
from __future__ import annotations

import html
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
# works from the repo (frontend/app.py) and from a sibling folder next to the repo
REPO = HERE.parent if (HERE.parent / "backend").is_dir() else HERE.parent / "hackaton2026"
sys.path.insert(0, str(REPO))

# Streamlit Cloud: copy secrets into environment variables so the backend (os.getenv) sees the API keys
import os  # noqa: E402
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, (str, int, float)) and not os.environ.get(_k):
            os.environ[_k] = str(_v)
except Exception:  # no secrets.toml locally: .env is used instead
    pass

from backend import (  # noqa: E402
    check_models, close_incident, get_analytics, get_dashboard_stats, get_incidents,
    get_lessons_learned, get_pending_reviews, get_recorded_runs, get_system_status, get_ticket,
    get_ticket_history, process_ticket, replay_ticket, review_ticket,
)
try:
    from backend import submit_feedback  # noqa: E402
except ImportError:  # older backend
    submit_feedback = None

st.set_page_config(page_title="UniResolve AI", page_icon="◆", layout="wide", initial_sidebar_state="collapsed")

# ---------------------------------------------------------------- theme: University of Debrecen green + gold, tech style
GREEN_DEEP = "#05130E"
GREEN_CARD = "rgba(16, 52, 39, 0.55)"
GREEN_SOLID = "#0D2C21"
GREEN_LINE = "rgba(120, 200, 160, 0.16)"
GREEN = "#1F8A5F"
EMERALD = "#2BD38F"
GOLD = "#F0C24B"
GOLD_SOFT = "#F7DB8A"
CREAM = "#EEF3EE"
MUTED = "#93ABA0"
ACCEPT = "#5FE3A8"
REJECT = "#FF8E6E"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
html, body, [class*="css"], .stApp {{ font-family: 'Inter', sans-serif; }}
.stApp {{
  color: {CREAM};
  background:
    radial-gradient(900px 500px at 12% -8%, rgba(43,211,143,.16), transparent 60%),
    radial-gradient(800px 480px at 92% 4%, rgba(240,194,75,.12), transparent 60%),
    linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px) 0 0 / 44px 44px,
    linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px) 0 0 / 44px 44px,
    {GREEN_DEEP};
  background-attachment: fixed;
}}
#MainMenu, footer, div[data-testid="stToolbarActions"], div[data-testid="stAppDeployButton"], div[data-testid="stMainMenu"] {{ display: none !important; }}
header[data-testid="stHeader"] {{ background: rgba(5,19,14,.80) !important; backdrop-filter: blur(16px) saturate(140%);
  -webkit-backdrop-filter: blur(16px) saturate(140%); border-bottom: 1px solid {GREEN_LINE}; height: 4.25rem; }}
header[data-testid="stHeader"] a p, header[data-testid="stHeader"] a > span:not([data-testid="stIconMaterial"]) {{
  font-family: 'Space Grotesk', sans-serif !important; font-weight: 600 !important; font-size: 1rem !important; }}
span[data-testid="stIconMaterial"], .material-symbols-rounded {{ font-family: 'Material Symbols Rounded' !important; }}
header[data-testid="stHeader"] a {{ transition: color .25s ease, background .25s ease; border-radius: 10px; }}
header[data-testid="stHeader"] a:hover {{ color: {GOLD} !important; background: rgba(240,194,75,.06) !important; }}
header[data-testid="stHeader"] a[aria-current="page"], header[data-testid="stHeader"] a[aria-current="page"] p {{ color: {GOLD} !important; }}
img[data-testid="stLogo"], div[data-testid="stLogo"] img {{ height: 2.6rem !important; }}
.block-container {{ padding-top: 5.2rem; padding-bottom: 4rem; max-width: 1360px; }}
h1, h2, h3 {{ font-family: 'Space Grotesk', sans-serif !important; color: {CREAM} !important; letter-spacing: -0.02em; }}
p, li, label, span, div {{ color: {CREAM}; }}

/* inputs */
.stTextArea textarea, .stTextInput input {{ background: rgba(5,19,14,.65) !important; color: {CREAM} !important;
  border: 1px solid {GREEN_LINE} !important; border-radius: 14px !important; font-size: 1.05rem; line-height: 1.5; }}
.stTextArea textarea:focus, .stTextInput input:focus {{ border-color: {GOLD} !important; box-shadow: 0 0 0 3px rgba(240,194,75,.18) !important; }}
div[data-baseweb="select"] > div {{ background: rgba(5,19,14,.65) !important; border-color: {GREEN_LINE} !important; border-radius: 12px !important; }}
label p {{ color: {MUTED} !important; font-size: .82rem !important; }}

/* buttons */
.stButton > button, div[data-testid="stPopover"] button {{ border-radius: 12px; border: 1px solid {GREEN_LINE}; background: rgba(16,52,39,.55);
  color: {CREAM}; font-weight: 600; backdrop-filter: blur(8px); transition: all .2s ease; }}
.stButton > button:hover, div[data-testid="stPopover"] button:hover {{ border-color: {GOLD}; color: {GOLD}; transform: translateY(-1px); }}
.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, {GOLD} 0%, #E3A92E 100%); color: #14110A; border: none;
  box-shadow: 0 8px 28px -8px rgba(240,194,75,.55); }}
.stButton > button[kind="primary"]:hover {{ box-shadow: 0 10px 34px -6px rgba(240,194,75,.75); color: #14110A; }}
.stButton > button[kind="primary"] p, .stButton > button[kind="primary"] span {{ color: #14110A !important; font-weight: 700; }}

/* metrics */
div[data-testid="stMetric"] {{ background: {GREEN_CARD}; backdrop-filter: blur(10px); border: 1px solid {GREEN_LINE};
  border-radius: 16px; padding: 16px 18px; }}
div[data-testid="stMetricLabel"] p {{ color: {MUTED} !important; font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; }}
div[data-testid="stMetricValue"] {{ color: {CREAM} !important; font-family: 'Space Grotesk', sans-serif; }}
.stExpander {{ border: 1px solid {GREEN_LINE} !important; border-radius: 14px !important; background: {GREEN_CARD}; backdrop-filter: blur(10px); }}
code, pre {{ font-family: 'JetBrains Mono', monospace !important; }}
.stCodeBlock pre, div[data-testid="stCode"] pre {{ background: rgba(5,19,14,.75) !important; border: 1px solid {GREEN_LINE}; border-radius: 14px; }}
div[data-testid="stDataFrame"] {{ border: 1px solid {GREEN_LINE}; border-radius: 14px; overflow: hidden; }}

/* smoothness */
[data-stale="true"] {{ opacity: 1 !important; filter: none !important; transition: none !important; }}
div[data-testid="stStatusWidget"], div[data-testid="stDecoration"] {{ display: none !important; }}
@keyframes pageIn {{ from {{ opacity: 0; transform: translateY(16px); }} to {{ opacity: 1; transform: none; }} }}
.page {{ animation: pageIn .45s cubic-bezier(.2,.75,.2,1) both; }}
.tl-item, .att, .card, .banner, .node {{ animation: pageIn .4s cubic-bezier(.2,.75,.2,1) both; }}
html {{ scroll-behavior: smooth; }}

/* top navigation: full width, sticky, text links */
div[data-testid="stHorizontalBlock"]:has(.nav-brand) {{
  position: sticky; top: 0; z-index: 1000; align-items: center;
  width: 100vw; margin-left: calc(50% - 50vw); padding: 10px max(28px, calc(50vw - 680px));
  background: rgba(5,19,14,.78); backdrop-filter: blur(16px) saturate(140%); -webkit-backdrop-filter: blur(16px) saturate(140%);
  border-bottom: 1px solid {GREEN_LINE}; margin-top: -1.1rem; margin-bottom: 34px; }}
.nav-brand {{ display:flex; align-items:center; gap:12px; height: 48px; }}
.logo {{ width:38px; height:38px; border-radius:11px; position:relative; flex: 0 0 38px;
  background: conic-gradient(from 210deg, {EMERALD}, {GOLD}, {GREEN}, {EMERALD}); box-shadow: 0 0 24px -6px rgba(43,211,143,.6); }}
.logo:after {{ content:"U"; position:absolute; inset:3px; border-radius:8px; background:{GREEN_DEEP}; display:flex; align-items:center;
  justify-content:center; font-family:'Space Grotesk',sans-serif; font-weight:700; color:{GOLD}; font-size:19px; }}
.nav-name {{ font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:1.18rem; line-height:1; letter-spacing:-.01em; }}
.nav-sub {{ font-size:.68rem; color:{MUTED}; letter-spacing:.1em; text-transform:uppercase; margin-top:4px; white-space:nowrap; }}
/* nav links = plain text buttons with animated underline */
div[data-testid="stHorizontalBlock"]:has(.nav-brand) div[class*="st-key-nav_"] button {{
  background: transparent !important; border: none !important; box-shadow: none !important; padding: 8px 4px !important;
  position: relative; transform: none !important; min-height: 0; }}
div[data-testid="stHorizontalBlock"]:has(.nav-brand) div[class*="st-key-nav_"] button p {{
  font-family:'Space Grotesk',sans-serif; font-weight:600; font-size:1rem !important; color:{CREAM} !important;
  transition: color .25s ease; white-space: nowrap; }}
div[data-testid="stHorizontalBlock"]:has(.nav-brand) div[class*="st-key-nav_"] button:hover p {{ color:{GOLD} !important; }}
div[data-testid="stHorizontalBlock"]:has(.nav-brand) div[class*="st-key-nav_"] button:after {{
  content:""; position:absolute; left:18%; right:18%; bottom:2px; height:2px; border-radius:2px;
  background: linear-gradient(90deg, {GOLD}, {EMERALD}); transform: scaleX(0); transform-origin: center;
  transition: transform .35s cubic-bezier(.2,.75,.2,1); }}
div[data-testid="stHorizontalBlock"]:has(.nav-brand) div[class*="st-key-nav_"] button:hover:after {{ transform: scaleX(.6); }}
div[data-testid="stHorizontalBlock"]:has(.nav-brand) div[data-testid="stPopover"] button {{
  background: linear-gradient(135deg, {GOLD}, #E3A92E) !important; color:#14110A !important; border:none !important;
  border-radius: 999px !important; font-weight:700; box-shadow: 0 8px 24px -10px rgba(240,194,75,.7); }}
div[data-testid="stHorizontalBlock"]:has(.nav-brand) div[data-testid="stPopover"] button p {{ color:#14110A !important; font-weight:700; }}
div[data-testid="stToggle"] label p {{ color:{CREAM} !important; font-weight:600; font-size:.88rem !important; }}
.engine {{ display:inline-flex; align-items:center; gap:8px; font-size:.8rem; color:{MUTED}; font-family:'JetBrains Mono',monospace; }}
.live-dot {{ width:8px; height:8px; border-radius:50%; background:{ACCEPT}; display:inline-block; animation: breathe 2.4s ease-in-out infinite; }}
.live-dot.off {{ background:{REJECT}; animation:none; }}
@keyframes breathe {{ 0%,100% {{ box-shadow:0 0 0 0 rgba(95,227,168,.55); }} 50% {{ box-shadow:0 0 0 6px rgba(95,227,168,0); }} }}

/* scroll reveal: every block rises in while it scrolls into view (CSS scroll-driven animation) */
@keyframes reveal {{ 0% {{ opacity: 0; transform: translateY(70px) scale(.965); filter: blur(7px); }}
                    70% {{ filter: blur(0); }}
                    100% {{ opacity: 1; transform: none; filter: none; }} }}
@supports (animation-timeline: view()) {{
  div[class*="st-key-pg_"] div[data-testid="stElementContainer"],
  div[class*="st-key-pg_"] div[data-testid="stHorizontalBlock"],
  .feat, .stat, .att, .tl-item, .step, .ornament {{
    animation-name: reveal; animation-fill-mode: both; animation-timing-function: cubic-bezier(.2,.7,.25,1);
    animation-timeline: view(); animation-range: entry 5% cover 30%; }}
  .feat:nth-child(3n+2), .stat:nth-child(4n+2) {{ animation-range: entry 12% cover 34%; }}
  .feat:nth-child(3n+3), .stat:nth-child(4n+3) {{ animation-range: entry 19% cover 38%; }}
  .stat:nth-child(4n+4) {{ animation-range: entry 26% cover 42%; }}
}}

/* cookie consent banner */
.st-key-consent {{ position: fixed !important; left: 16px !important; right: 16px !important; bottom: 40px;
  margin: 0 auto !important; z-index: 2000; width: auto !important; max-width: 780px; background: rgba(8,28,21,.97); backdrop-filter: blur(18px);
  border: 1px solid rgba(240,194,75,.55); border-radius: 22px; padding: 26px 28px 22px !important;
  box-shadow: 0 30px 80px -20px rgba(0,0,0,.9), 0 0 0 1px rgba(240,194,75,.08);
  animation: pageSwap .5s cubic-bezier(.2,.75,.2,1) both; overflow: visible !important; height: auto !important; }}
.ck-title {{ font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:1.45rem; color:{GOLD}; margin-bottom:8px; }}
.ck-text {{ font-size:1.05rem; color:{CREAM}; line-height:1.55; margin-bottom:10px; }}
.st-key-consent .stButton > button {{ min-height: 3.1rem; font-size: 1.05rem; }}
.st-key-consent .stButton > button p {{ font-size: 1.05rem !important; font-weight: 700; }}
@media (max-width: 640px) {{ .st-key-consent {{ bottom: 90px; left: 12px !important; right: 12px !important;
  padding: 20px 18px 16px !important; }}
  .st-key-consent div[data-testid="stHorizontalBlock"] {{ flex-direction: column !important; gap: 8px !important; }}
  .st-key-consent div[data-testid="stColumn"] {{ width: 100% !important; flex: 1 1 auto !important; }}
  .ck-title {{ font-size:1.2rem; }} .ck-text {{ font-size:.95rem; }} }}
div[data-testid="stElementContainer"]:has(iframe[title*="extra_streamlit_components"]),
div[data-testid="stElementContainer"]:has(iframe[title*="cookie"]) {{ height: 0 !important; overflow: hidden; margin: 0 !important; }}

/* page transition: every page lives in its own keyed container, re-mounted on navigation */
@keyframes pageSwap {{ 0% {{ opacity: 0; transform: translateY(22px); filter: blur(8px); }}
                      60% {{ filter: blur(0); }} 100% {{ opacity: 1; transform: none; filter: none; }} }}
div[class*="st-key-pg_"] {{ animation: pageSwap .6s cubic-bezier(.2,.75,.2,1) both; }}
div[class*="st-key-pg_"] > div > div:nth-child(2) {{ animation: pageSwap .6s .06s cubic-bezier(.2,.75,.2,1) both; }}
div[class*="st-key-pg_"] > div > div:nth-child(3) {{ animation: pageSwap .6s .12s cubic-bezier(.2,.75,.2,1) both; }}

/* Debrecen motifs */
.hero-wrap {{ display:grid; grid-template-columns: 1.15fr .85fr; gap: 28px; align-items: end; }}
.skyline {{ width: 100%; height: auto; opacity: .9; animation: floaty 7s ease-in-out infinite; }}
.skyline .ln {{ fill: none; stroke: {GOLD}; stroke-width: 1.6; stroke-linejoin: round; stroke-linecap: round; opacity:.75; }}
.skyline .ln2 {{ fill: none; stroke: {EMERALD}; stroke-width: 1.2; opacity:.5; }}
.skyline .draw {{ stroke-dasharray: 1400; stroke-dashoffset: 1400; animation: draw 2.6s .2s cubic-bezier(.4,0,.2,1) forwards; }}
@keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
@keyframes floaty {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-6px); }} }}
.heritage {{ display:inline-flex; align-items:center; gap:10px; padding:6px 14px 6px 8px; border-radius:999px;
  border:1px solid rgba(240,194,75,.35); background: rgba(240,194,75,.06); font-family:'JetBrains Mono',monospace;
  font-size:.75rem; color:{GOLD}; margin-left:8px; }}
.ornament {{ display:flex; justify-content:center; margin: 46px 0 8px; opacity:.85; }}
.ornament svg path, .ornament svg circle {{ fill:none; stroke:{GOLD}; stroke-width:1.4; stroke-linecap:round; }}
.ornament svg .f {{ fill:{GOLD}; stroke:none; opacity:.9; }}
@media (max-width: 1000px) {{ .hero-wrap {{ grid-template-columns: 1fr; }} .skyline {{ max-width: 520px; }} }}
/* mobile: compact controls row, smaller hero */
.st-key-ctrl div[data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; flex-direction: row !important; gap: 10px !important; }}
.st-key-ctrl div[data-testid="stColumn"] {{ min-width: 0 !important; }}
@media (max-width: 640px) {{
  .st-key-ctrl div[data-testid="stColumn"]:first-child {{ display: none !important; }}
  .st-key-ctrl div[data-testid="stColumn"] {{ width: auto !important; flex: 1 1 0 !important; }}
  .block-container {{ padding-top: 4.6rem !important; padding-left: 1rem !important; padding-right: 1rem !important; }}
  .hero-h {{ font-size: 2.1rem !important; }}
  .hero-k, .heritage {{ font-size: .68rem !important; margin: 4px 4px 0 0 !important; }}
  .bigq {{ font-size: 1.45rem !important; }}
  .pipe {{ padding: 14px 8px !important; }}
  .node {{ min-width: 64px !important; }}
  .orb {{ width: 42px !important; height: 42px !important; border-radius: 12px !important; font-size: 1rem !important; }}
  .link {{ flex-basis: 10px !important; }}
  .nname {{ font-size: .72rem !important; }}
  .stat .v {{ font-size: 2rem !important; }}
}}

/* landing sections */
.feats {{ display:grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
.feat {{ background:{GREEN_CARD}; backdrop-filter: blur(12px); border:1px solid {GREEN_LINE}; border-radius:20px; padding: 22px 22px 20px;
  transition: transform .35s cubic-bezier(.2,.75,.2,1), border-color .35s ease; }}
.feat:hover {{ transform: translateY(-4px); border-color: rgba(240,194,75,.45); }}
.feat .fi {{ width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center; margin-bottom:14px;
  font-family:'Space Grotesk',sans-serif; font-weight:700; color:#14110A; background: linear-gradient(135deg, {GOLD}, {EMERALD}); }}
.feat h3 {{ font-size:1.12rem !important; margin:0 0 6px !important; }}
.feat p {{ color:{MUTED} !important; font-size:.93rem; line-height:1.5; margin:0; }}
.stats {{ display:grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }}
.stat {{ border-radius:20px; padding: 22px; border:1px solid {GREEN_LINE};
  background: linear-gradient(160deg, rgba(240,194,75,.08), rgba(43,211,143,.05)); }}
.stat .v {{ font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:2.6rem; line-height:1;
  background: linear-gradient(100deg, {GOLD}, {EMERALD}); -webkit-background-clip:text; background-clip:text; color:transparent !important; }}
.stat .l {{ color:{MUTED}; font-size:.88rem; margin-top:8px; }}
.bigq {{ font-family:'Space Grotesk',sans-serif; font-size: 2rem; line-height:1.2; letter-spacing:-.02em; max-width: 900px; }}
@media (max-width: 900px) {{ .feats, .stats {{ grid-template-columns: 1fr; }} }}

/* hero */
.hero-k {{ display:inline-flex; gap:8px; align-items:center; font-family:'JetBrains Mono',monospace; font-size:.76rem; color:{GOLD};
  border:1px solid rgba(240,194,75,.35); border-radius:999px; padding:5px 12px; background: rgba(240,194,75,.07); }}
.hero-h {{ font-family:'Space Grotesk',sans-serif; font-weight:700; font-size: 3.0rem; line-height:1.05; letter-spacing:-.03em; margin: 14px 0 10px; }}
.grad {{ background: linear-gradient(100deg, {CREAM} 10%, {GOLD} 55%, {EMERALD} 95%); -webkit-background-clip:text; background-clip:text; color:transparent !important; }}
.hero-p {{ color:{MUTED}; font-size:1.08rem; max-width: 760px; line-height:1.55; }}
.page-h {{ font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:2.2rem; letter-spacing:-.02em; margin: 6px 0 4px; }}

/* generic */
.pill {{ display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:999px; font-size:.74rem; font-weight:600;
  border:1px solid {GREEN_LINE}; background: rgba(5,19,14,.6); color:{CREAM}; white-space:nowrap; font-family:'JetBrains Mono',monospace; }}
.pill.gold {{ border-color:rgba(240,194,75,.55); color:{GOLD}; }}
.pill.ok {{ border-color:rgba(95,227,168,.55); color:{ACCEPT}; }}
.pill.bad {{ border-color:rgba(255,142,110,.55); color:{REJECT}; }}
.pill.sim {{ background:{REJECT}; color:#2A0F05; border:none; }}
.dot {{ width:8px; height:8px; border-radius:50%; background:{ACCEPT}; display:inline-block; }}
.dot.off {{ background:{REJECT}; }}
.section {{ font-family:'Space Grotesk',sans-serif; font-weight:600; font-size:1.25rem; margin: 26px 0 12px; display:flex; align-items:center; gap:10px; }}
.section:before {{ content:""; width:4px; height:18px; border-radius:2px; background: linear-gradient({GOLD}, {EMERALD}); }}
.kicker {{ font-size:.7rem; letter-spacing:.16em; text-transform:uppercase; color:{GOLD}; font-weight:700; font-family:'JetBrains Mono',monospace; }}
.card {{ background:{GREEN_CARD}; backdrop-filter: blur(12px); border:1px solid {GREEN_LINE}; border-radius:18px; padding:18px 20px; }}
.small {{ color:{MUTED}; font-size:.82rem; }}
.meta {{ color:{MUTED}; font-size:.76rem; font-family:'JetBrains Mono',monospace; }}

/* agent pipeline */
.pipe {{ display:flex; align-items:center; gap:0; padding: 20px 18px; border-radius:20px; background:{GREEN_CARD};
  backdrop-filter: blur(12px); border:1px solid {GREEN_LINE}; overflow-x:auto; }}
.node {{ min-width: 128px; flex:1; display:flex; flex-direction:column; align-items:center; gap:8px; text-align:center; }}
.orb {{ width:54px; height:54px; border-radius:16px; display:flex; align-items:center; justify-content:center; position:relative;
  font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:1.15rem; color:{MUTED};
  background: rgba(5,19,14,.8); border:1px solid {GREEN_LINE}; transition: all .3s ease; }}
.orb.run {{ color:#14110A; background:{GOLD}; border-color:{GOLD}; box-shadow: 0 0 0 0 rgba(240,194,75,.6); animation: ring 1.1s ease-out infinite; }}
.orb.done {{ color:#062016; background:{ACCEPT}; border-color:{ACCEPT}; box-shadow: 0 0 22px -4px rgba(95,227,168,.7); }}
.orb.bad {{ color:#2A0F05; background:{REJECT}; border-color:{REJECT}; box-shadow: 0 0 22px -4px rgba(255,142,110,.7); }}
.orb.skip {{ opacity:.35; }}
@keyframes ring {{ 0% {{ box-shadow:0 0 0 0 rgba(240,194,75,.65); }} 100% {{ box-shadow:0 0 0 14px rgba(240,194,75,0); }} }}
.orb .cnt {{ position:absolute; top:-8px; right:-8px; background:{GREEN_DEEP}; border:1px solid {GOLD}; color:{GOLD};
  font-size:.66rem; border-radius:999px; padding:1px 6px; font-family:'JetBrains Mono',monospace; }}
.nname {{ font-weight:600; font-size:.86rem; }}
.nstate {{ font-size:.7rem; color:{MUTED}; font-family:'JetBrains Mono',monospace; min-height: 1em; }}
.link {{ flex: 0 0 34px; height:2px; background:{GREEN_LINE}; margin-bottom: 38px; position:relative; overflow:hidden; border-radius:2px; }}
.link.on {{ background: linear-gradient(90deg, {ACCEPT}, {GOLD}); }}
.link.flow:after {{ content:""; position:absolute; inset:0; width:40%; background: linear-gradient(90deg, transparent, {GOLD}, transparent);
  animation: flow 1s linear infinite; }}
@keyframes flow {{ from {{ transform: translateX(-100%); }} to {{ transform: translateX(260%); }} }}

/* timeline */
.tl {{ position:relative; }}
.tl-item {{ position:relative; padding: 0 0 12px 36px; }}
.tl-item:before {{ content:""; position:absolute; left:12px; top:30px; bottom:0; width:2px; background:{GREEN_LINE}; }}
.tl-item:last-child:before {{ display:none; }}
.tl-badge {{ position:absolute; left:0; top:6px; width:26px; height:26px; border-radius:8px; background:rgba(5,19,14,.9);
  border:1px solid {GREEN_LINE}; color:{ACCEPT}; font-size:.72rem; font-weight:700; display:flex; align-items:center; justify-content:center;
  font-family:'JetBrains Mono',monospace; }}
.tl-badge.run {{ background:{GOLD}; color:#14110A; border-color:{GOLD}; animation: ring 1.1s ease-out infinite; }}
.tl-badge.err {{ background:{REJECT}; color:#2A0F05; }}
.tl-card {{ background:{GREEN_CARD}; backdrop-filter: blur(10px); border:1px solid {GREEN_LINE}; border-radius:14px; padding:12px 16px; }}
.tl-card.run {{ border-color: rgba(240,194,75,.6); }}
.tl-head {{ display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; }}
.tl-agent {{ font-weight:700; font-size:.98rem; font-family:'Space Grotesk',sans-serif; }}
.tl-action {{ color:{MUTED}; font-size:.85rem; margin-top:2px; }}
.tl-sum {{ margin-top:6px; font-size:.93rem; }}
.tl-dec {{ margin-top:8px; padding:8px 12px; border-radius:10px; background: rgba(5,19,14,.6); font-size:.84rem; border-left:3px solid {GOLD}; }}
.tl-dec.ok {{ border-left-color:{ACCEPT}; }}
.tl-dec.bad {{ border-left-color:{REJECT}; }}

/* decision loop */
.loop {{ display:flex; gap:12px; flex-wrap:wrap; align-items:stretch; }}
.att {{ flex:1; min-width:260px; background:{GREEN_CARD}; backdrop-filter: blur(10px); border:1px solid {GREEN_LINE}; border-radius:16px; padding:16px 18px; }}
.att.ok {{ border-color: rgba(95,227,168,.6); box-shadow: 0 0 40px -22px rgba(95,227,168,.8); }}
.att.bad {{ border-color: rgba(255,142,110,.6); box-shadow: 0 0 40px -22px rgba(255,142,110,.8); }}
.att h4 {{ margin:0 0 6px; font-family:'Space Grotesk',sans-serif; font-size:.95rem; color:{MUTED}; font-weight:600; }}
.verdict {{ font-family:'Space Grotesk',sans-serif; font-weight:700; letter-spacing:.04em; font-size:1.5rem; }}
.verdict.ok {{ color:{ACCEPT}; }} .verdict.bad {{ color:{REJECT}; }}
.chk {{ font-size:.84rem; margin:3px 0; }}
.arrow {{ display:flex; align-items:center; color:{GOLD}; font-size:1.5rem; padding:0 2px; }}

.step {{ display:flex; gap:12px; padding:11px 0; border-bottom:1px solid {GREEN_LINE}; }}
.step:last-child {{ border-bottom:none; }}
.stepn {{ min-width:28px; height:28px; border-radius:9px; background: linear-gradient(135deg, {GOLD}, #E3A92E); color:#14110A; font-weight:800;
  display:flex; align-items:center; justify-content:center; font-size:.82rem; font-family:'JetBrains Mono',monospace; }}
.status-big {{ font-family:'Space Grotesk',sans-serif; font-size:1.4rem; }}
.banner {{ border-radius:14px; padding:12px 16px; margin: 8px 0 14px; font-weight:600; font-size:.92rem; backdrop-filter: blur(8px); }}
.banner.sim {{ background:rgba(255,142,110,.10); border:1px solid {REJECT}; color:{REJECT}; }}
.banner.inc {{ background:rgba(240,194,75,.10); border:1px solid {GOLD}; color:{GOLD}; }}
.banner.rec {{ background:rgba(95,227,168,.08); border:1px solid {ACCEPT}; color:{ACCEPT}; }}
.footer {{ margin-top: 48px; padding-top: 16px; border-top:1px solid {GREEN_LINE}; display:flex; justify-content:space-between;
  color:{MUTED}; font-size:.78rem; font-family:'JetBrains Mono',monospace; }}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- Debrecen line art (drawn for this app)
SKYLINE_SVG = """<svg class="skyline" viewBox="0 0 520 250" xmlns="http://www.w3.org/2000/svg" aria-label="Debrecen skyline line art">
<path class="ln2" d="M10 228 H510"/>
<g class="draw ln">
<path d="M40 228 V120 H64 V98 l12 -22 l12 22 V120 H88"/>
<path d="M76 60 V76 M71 66 H81"/>
<path d="M88 120 V112 L150 74 L212 112 V120"/>
<path d="M212 120 H212 V98 l12 -22 l12 22 V120 H260 V228"/>
<path d="M224 60 V76 M219 66 H229"/>
<path d="M88 228 V124 H212 V228"/>
<path d="M104 228 V136 M124 228 V136 M144 228 V136 M156 228 V136 M176 228 V136 M196 228 V136"/>
<path d="M96 132 H204"/>
<path d="M138 228 V196 a12 12 0 0 1 24 0 V228"/>
<circle cx="150" cy="100" r="7"/>
<path d="M48 140 h10 M48 160 h10 M242 140 h10 M242 160 h10"/>
</g>
<g class="draw ln" style="animation-delay:.6s">
<path d="M280 228 V150 H330 V136 H350 V150"/>
<path d="M350 150 V112 H378 V92 l14 -18 l14 18 V112 H434 V150"/>
<path d="M392 60 V74 M387 66 H397"/>
<path d="M434 150 V136 H454 V150 H504 V228"/>
<path d="M280 150 H504"/>
<path d="M296 228 V168 M316 228 V168 M336 228 V168 M448 228 V168 M468 228 V168 M488 228 V168"/>
<path d="M360 228 V160 H424 V228"/>
<path d="M372 228 V176 M384 228 V176 M400 228 V176 M412 228 V176"/>
<path d="M380 128 h24 M380 100 a12 12 0 0 1 24 0"/>
</g>
<g class="draw ln2" style="animation-delay:1.1s"><path d="M18 228 c6 -18 14 -26 14 -38 c0 12 8 20 14 38"/><path d="M262 228 c6 -14 10 -20 10 -30 c0 10 4 16 10 30"/></g>
</svg>"""

BOOK_SVG = """<svg width="18" height="14" viewBox="0 0 18 14" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<path d="M1 2.2 C4 1 6.6 1.2 9 2.6 C11.4 1.2 14 1 17 2.2 V12.4 C14 11.2 11.4 11.4 9 12.8 C6.6 11.4 4 11.2 1 12.4 Z" fill="none" stroke="#F0C24B" stroke-width="1.3" stroke-linejoin="round"/>
<path d="M9 2.6 V12.8" stroke="#F0C24B" stroke-width="1.1"/></svg>"""

ORNAMENT = """<div class="ornament reveal"><svg width="300" height="40" viewBox="0 0 300 40" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<path d="M10 20 H112 M188 20 H290"/>
<path d="M150 6 c-8 6 -9 14 0 26 c9 -12 8 -20 0 -26 z" class="f"/>
<path d="M150 30 c-10 -2 -18 -8 -22 -18 c8 2 16 8 22 18 z" class="f" opacity=".75"/>
<path d="M150 30 c10 -2 18 -8 22 -18 c-8 2 -16 8 -22 18 z" class="f" opacity=".75"/>
<path d="M120 20 c-4 -6 -10 -6 -12 0 c2 6 8 6 12 0 z M180 20 c4 -6 10 -6 12 0 c-2 6 -8 6 -12 0 z" class="f" opacity=".6"/>
<circle cx="100" cy="20" r="2.2" class="f"/><circle cx="200" cy="20" r="2.2" class="f"/>
</svg></div>"""

e = html.escape

AGENT_ABBR = {"Triage Agent": "T", "Incident Agent": "I", "Routing Agent": "R", "Resolution Agent": "P",
              "Auditor Agent": "A", "Communication Agent": "C", "Orchestrator": "O", "Human Reviewer": "H"}
STATUS_TEXT = {
    "solution_verified": ("Verified plan ready", "ok"),
    "awaiting_human_approval": ("Waiting for staff approval", "gold"),
    "escalated_to_human": ("Escalated to a human", "bad"),
    "approved_by_staff": ("Approved by staff", "ok"),
    "rejected_by_staff": ("Rejected by staff", "bad"),
    "out_of_scope_request": ("Not a support request", "gold"),
    "failed": ("Failed", "bad"),
}
EXAMPLES = [
    "University Wi-Fi is not working and my exam starts in one hour!",
    "There is a broken chair in classroom 204.",
    "I was sick and need to reschedule my calculus exam to a new date.",
    "The elevator in building C is broken and I use a wheelchair.",
]
CATEGORIES = ["(let the agents decide)", "it_network", "it_accounts", "facilities", "classroom_equipment",
              "exams_academic", "administration", "finance", "safety", "health", "wellbeing", "accessibility",
              "conduct", "housing", "international", "library", "campus_services", "transport", "other"]


def pill(text: str, kind: str = "") -> str:
    return f'<span class="pill {kind}">{e(str(text))}</span>'


def fmt_time(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%H:%M:%S")
    except ValueError:
        return iso


# ---------------------------------------------------------------- timeline rendering
def render_timeline(events: list[dict]) -> str:
    steps: dict[int, dict] = {}
    order: list[int] = []
    pre: list[dict] = []
    for ev in events:
        s = ev.get("step", 0)
        if ev.get("status") == "decision":
            if s in steps:
                steps[s].setdefault("decisions", []).append(ev)
            else:
                pre.append(ev)
            continue
        if s not in steps:
            steps[s] = {}
            order.append(s)
        steps[s].update({k: v for k, v in ev.items() if v is not None})
        steps[s].setdefault("decisions", [])
    out = ['<div class="tl">']
    for ev in pre:
        out.append(_decision_html(ev, standalone=True))
    for s in order:
        d = steps[s]
        st_ = d.get("status")
        badge_cls = "run" if st_ == "started" else ("err" if st_ == "error" else "")
        card_cls = "run" if st_ == "started" else ""
        chips = []
        if st_ == "started":
            chips.append(pill("running", "gold"))
        elif st_ == "completed":
            if d.get("simulated"):
                chips.append(pill("SIMULATED", "sim"))
            else:
                chips.append(pill(f"{d.get('provider', '')} · {d.get('model', '')}"))
            chips.append(f'<span class="meta">{d.get("duration_ms", 0)} ms</span>')
            if d.get("replay"):
                chips.append(pill("recorded", "ok"))
        elif st_ == "error":
            chips.append(pill("error", "bad"))
        summary = f'<div class="tl-sum">{e(d.get("summary", ""))}</div>' if d.get("summary") else ""
        fb = "".join(f'<div class="meta">fallback: {e(x[:110])}</div>' for x in (d.get("fallback_errors") or [])[:2])
        decs = "".join(_decision_html(x) for x in d.get("decisions", []))
        out.append(f'''<div class="tl-item"><div class="tl-badge {badge_cls}">{AGENT_ABBR.get(d.get("agent"), "•")}</div>
<div class="tl-card {card_cls}"><div class="tl-head"><div><div class="tl-agent">{e(d.get("agent", ""))}</div>
<div class="tl-action">{e(d.get("action", ""))}</div></div><div>{" ".join(chips)}</div></div>{summary}{fb}{decs}</div></div>''')
    out.append("</div>")
    return "".join(out)


def _decision_html(ev: dict, standalone: bool = False) -> str:
    dec = str(ev.get("decision", ""))
    kind = "ok" if dec in ("ACCEPT", "FINALIZE", "APPROVE", "NO_INCIDENT") else (
        "bad" if dec in ("REJECT", "ESCALATE_TO_HUMAN", "INJECTION_FLAGGED", "OUT_OF_SCOPE") else "")
    body = e(ev.get("summary", ""))
    html_ = f'<div class="tl-dec {kind}"><b>{e(ev.get("agent", ""))}</b> → <b>{e(dec)}</b><br><span class="small">{body}</span></div>'
    return f'<div class="tl-item"><div class="tl-badge">O</div>{html_}</div>' if standalone else html_


# ---------------------------------------------------------------- result rendering
def render_result(r: dict, recorded: bool = False) -> None:
    if not r:
        return
    status = r.get("status")
    label, kind = STATUS_TEXT.get(status, (status, ""))
    if recorded:
        st.markdown(f'<div class="banner rec">RECORDED RUN · recorded at {fmt_time(r.get("recorded_at"))} · '
                    'played back from the log, no LLM was called now</div>', unsafe_allow_html=True)
    if r.get("execution_mode") and r.get("execution_mode") != "live_llm":
        st.markdown('<div class="banner sim">OFFLINE SIMULATION · some or all agent outputs in this case were '
                    'produced by the deterministic fallback, not a live LLM</div>', unsafe_allow_html=True)
    inc = r.get("incident")
    if inc:
        st.markdown(f'<div class="banner inc">Part of campus incident {e(inc["incident_id"])}: {e(inc["title"])} · '
                    f'{inc["report_count"]} reports</div>', unsafe_allow_html=True)
    if status == "failed":
        st.error(r.get("error") or "Processing failed")
        return

    # decision loop
    attempts = (r.get("agent_results") or {}).get("resolution_attempts") or []
    if attempts:
        st.markdown('<div class="section">Autonomous decision loop</div>', unsafe_allow_html=True)
        parts = []
        for i, a in enumerate(attempts):
            au = a.get("audit") or {}
            ok = au.get("verdict") == "ACCEPT"
            checks = "".join(
                f'<div class="chk">{"✓" if c["passed"] else "✗"} <b>{e(c["id"])}</b> {e(c["name"])}'
                + ("" if c["passed"] else f'<br><span class="small">{e(c["detail"])}</span>') + "</div>"
                for c in au.get("programmatic_checks") or [])
            llm_issues = "".join(f'<div class="chk small">LLM: {e(x)}</div>' for x in (au.get("issues") or [])[:2]) \
                if au.get("llm_verdict") == "REJECT" else ""
            lessons = a.get("solution", {}).get("lessons_applied") or []
            les = f'<div class="small" style="margin-top:6px">Applied {len(lessons)} lesson(s) from past rejections</div>' if lessons else ""
            title = "Draft plan" if i == 0 else f"Revision {i}"
            parts.append(f'''<div class="att {'ok' if ok else 'bad'}"><h4>{title}</h4>
<div class="verdict {'ok' if ok else 'bad'}">{'ACCEPT' if ok else 'REJECT'}</div>
<div class="small">{au.get("checks_passed", 0)}/{au.get("checks_total", 0)} code checks · LLM auditor: {e(str(au.get("llm_verdict", "")))}</div>
<div style="margin-top:8px">{checks}{llm_issues}</div>{les}</div>''')
            if i < len(attempts) - 1:
                parts.append('<div class="arrow">→</div>')
        st.markdown(f'<div class="loop">{"".join(parts)}</div>', unsafe_allow_html=True)

    # final resolution
    st.markdown('<div class="section">Final resolution</div>', unsafe_allow_html=True)
    fs = r.get("final_solution") or {}
    c1, c2 = st.columns([1.35, 1])
    with c1:
        steps_html = "".join(
            f'<div class="step"><div class="stepn">{i}</div><div>{e(s["action"])}'
            f'<div class="meta">{e(s.get("owner") or "")} · {e(s.get("kb_ref") or "no source")}</div></div></div>'
            for i, s in enumerate(fs.get("steps") or [], 1))
        tca = "".join(f"<li>{e(x)}</li>" for x in fs.get("time_critical_actions") or [])
        tca_html = f'<div class="kicker" style="margin-top:12px">Do this first</div><ul>{tca}</ul>' if tca else ""
        st.markdown(f'''<div class="card"><div class="kicker">Plan</div>
<div style="margin:6px 0 4px">{e(fs.get("diagnosis", ""))}</div>{tca_html}{steps_html}
<div class="small" style="margin-top:10px">{e(fs.get("note", ""))}</div></div>''', unsafe_allow_html=True)
    with c2:
        st.markdown(f'''<div class="card"><div class="kicker">Case {e(r.get("ticket_id", ""))}</div>
<div class="status-big" style="margin:6px 0">{pill(label, kind)}</div>
<div style="display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin-top:10px">
<span class="small">Category</span><span>{e(str(r.get("category")))}</span>
<span class="small">Priority</span><span>{e(str(r.get("priority")))}</span>
<span class="small">Department</span><span>{e(str(r.get("assigned_department")))}</span>
<span class="small">Location</span><span>{e(str(r.get("location") or "-"))}</span>
<span class="small">Language</span><span>{e(str(r.get("language") or "-"))}</span>
<span class="small">Auditor</span><span>{e(str(r.get("auditor_decision")))}</span>
<span class="small">Revisions</span><span>{r.get("revision_count", 0)}</span>
</div>{('<div style="margin-top:10px">' + pill("security flag: instruction-like text treated as data", "bad") + '</div>') if (r.get("input_guard") or {}).get("injection_suspected") else ""}
</div>''', unsafe_allow_html=True)
        hr = r.get("human_review")
        if hr:
            st.markdown(f'<div class="card" style="margin-top:12px"><div class="kicker">Staff decision</div>'
                        f'{pill(hr["decision"], "ok" if hr["decision"] == "APPROVE" else "bad")} '
                        f'<span class="small">by {e(hr["reviewer"])} · {fmt_time(hr["reviewed_at"])}</span>'
                        f'<div style="margin-top:6px">{e(hr.get("note") or "")}</div></div>', unsafe_allow_html=True)

    md = r.get("message_draft")
    if md:
        st.markdown('<div class="section">Ready-to-send message</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="small">To <b>{e(md["to_department"])}</b> · via {e(md.get("channel") or "")}'
                    + (' · rewritten after a claim check' if md.get("self_corrected") else "") + "</div>",
                    unsafe_allow_html=True)
        st.code(f"Subject: {md['subject']}\n\n{md['body']}", language=None)

    if submit_feedback and not recorded and r.get("ticket_id") and status != "out_of_scope_request":
        render_feedback(r)

    m = r.get("autonomy_metrics") or {}
    if m:
        st.markdown('<div class="section">Autonomy metrics</div>', unsafe_allow_html=True)
        cols = st.columns(6)
        vals = [("Agents run", m.get("agents_executed")), ("Decisions", m.get("autonomous_decisions")),
                ("Rejections", m.get("auditor_rejections")), ("Revisions", m.get("revision_attempts")),
                ("Human hand-offs", m.get("human_escalations")),
                ("Time", f'{(m.get("total_execution_time_ms") or 0) / 1000:.1f} s')]
        for col, (k, v) in zip(cols, vals):
            col.metric(k, v)
        st.markdown(f'<div class="small">Live LLM calls: {m.get("llm_calls_live", 0)} · simulated: '
                    f'{m.get("llm_calls_simulated", 0)} · {e(r.get("kb_notice", ""))}</div>', unsafe_allow_html=True)

    with st.expander("Full execution trace"):
        st.markdown(render_timeline(r.get("execution_trace") or []), unsafe_allow_html=True)




def render_feedback(r: dict) -> None:
    tid = r["ticket_id"]
    fb = r.get("student_feedback")
    st.markdown('<div class="section">Was this helpful?</div>', unsafe_allow_html=True)
    if fb:
        txt = "Thanks! Marked as helpful." if fb["rating"] == "up" else \
            "Thanks. Your comment is now a lesson the agents use for future plans in this category."
        st.markdown(f'<div class="card"><span class="pill {"ok" if fb["rating"] == "up" else "gold"}">'
                    f'{"helpful" if fb["rating"] == "up" else "not helpful"}</span>&nbsp; {e(txt)}'
                    + (f'<div class="small" style="margin-top:6px">“{e(fb["comment"])}”</div>' if fb.get("comment") else "")
                    + '</div>', unsafe_allow_html=True)
        return
    c1, c2, c3 = st.columns([1, 1, 4], vertical_alignment="bottom")
    if c1.button("👍  Helpful", key=f"up_{tid}", use_container_width=True):
        updated = submit_feedback(tid, "up")
        _store(updated)
        st.rerun()
    comment = c3.text_input("What was missing? (optional, it teaches the agents)", key=f"cm_{tid}",
                            placeholder="e.g. it did not say how long the repair takes")
    if c2.button("👎  Not helpful", key=f"down_{tid}", use_container_width=True):
        updated = submit_feedback(tid, "down", comment)
        _store(updated)
        st.rerun()


def _store(updated: dict) -> None:
    lr = st.session_state.get("last_result")
    if lr and lr.get("ticket_id") == updated.get("ticket_id"):
        st.session_state["last_result"] = updated


# ---------------------------------------------------------------- live agent pipeline
PIPE = [("Triage Agent", "Triage", "T"), ("Incident Agent", "Incident", "I"), ("Routing Agent", "Routing", "R"),
        ("Resolution Agent", "Resolution", "P"), ("Auditor Agent", "Auditor", "A"),
        ("Communication Agent", "Message", "C")]


def render_pipeline(events: list[dict], finished: bool = False) -> str:
    state = {a: {"st": "idle", "n": 0, "verdict": None, "label": ""} for a, _, _ in PIPE}
    for ev in events:
        a = ev.get("agent")
        if a not in state:
            continue
        s = state[a]
        if ev.get("status") == "started":
            s["st"], s["label"] = "run", "working…"
        elif ev.get("status") == "completed":
            s["n"] += 1
            s["st"] = "done"
            s["label"] = f'{ev.get("duration_ms", 0)} ms' if not ev.get("simulated") else "simulated"
            if a == "Auditor Agent":
                v = (ev.get("output") or {}).get("verdict")
                s["verdict"] = v
                s["st"] = "done" if v == "ACCEPT" else "bad"
                s["label"] = v or s["label"]
        elif ev.get("status") == "error":
            s["st"], s["label"] = "bad", "error"
    incident_used = state["Incident Agent"]["n"] > 0 or state["Incident Agent"]["st"] == "run"
    parts = []
    nodes = [p for p in PIPE if p[0] != "Incident Agent" or incident_used]
    for i, (agent, name, abbr) in enumerate(nodes):
        s = state[agent]
        cls = {"run": "run", "done": "done", "bad": "bad"}.get(s["st"], "")
        if finished and s["st"] == "idle":
            cls = "skip"
        cnt = f'<span class="cnt">×{s["n"]}</span>' if s["n"] > 1 else ""
        parts.append(f'<div class="node"><div class="orb {cls}">{abbr}{cnt}</div><div class="nname">{name}</div>'
                     f'<div class="nstate">{e(s["label"])}</div></div>')
        if i < len(nodes) - 1:
            nxt = state[nodes[i + 1][0]]
            link = "on" if nxt["st"] in ("done", "bad") else ("on flow" if nxt["st"] == "run" else "")
            parts.append(f'<div class="link {link}"></div>')
    return f'<div class="pipe">{"".join(parts)}</div>'


def live_runner(pipe_ph, tl_ph):
    events: list[dict] = []

    def on_event(ev: dict) -> None:
        events.append(ev)
        pipe_ph.markdown(render_pipeline(events), unsafe_allow_html=True)
        tl_ph.markdown(render_timeline(events), unsafe_allow_html=True)
    return on_event

# ---------------------------------------------------------------- navigation + global controls
status = get_system_status()

# anonymous visitor id: each visitor sees their own case history.
# With cookie consent the id is kept in a first-party cookie for a year; otherwise only for the session.
VID_COOKIE, CONSENT_COOKIE = "ur_vid", "ur_consent"
try:
    _cookies = dict(st.context.cookies)
except Exception:
    _cookies = {}
if "visitor" not in st.session_state:
    import uuid
    consent = _cookies.get(CONSENT_COOKIE)
    vid = _cookies.get(VID_COOKIE) if consent == "yes" else None
    vid = vid or st.query_params.get("v") or uuid.uuid4().hex[:10]
    st.session_state["visitor"] = "".join(ch for ch in str(vid) if ch.isalnum())[:32] or uuid.uuid4().hex[:10]
    st.session_state["consent"] = consent if consent in ("yes", "no") else None
try:
    if st.query_params.get("v") != st.session_state["visitor"]:
        st.query_params["v"] = st.session_state["visitor"]
except Exception:
    pass

try:
    import extra_streamlit_components as stx
    _cookie_manager = stx.CookieManager(key="ur_cookie_manager")
except Exception:  # library missing: consent still works for the session
    _cookie_manager = None

# second way to read the cookies (the component reports them a moment after the page loads)
if _cookie_manager and not st.session_state.get("cookie_checked"):
    try:
        _all = _cookie_manager.get_all(key="ur_get_all") or {}
    except Exception:
        _all = {}
    if _all:
        st.session_state["cookie_checked"] = True
        if _all.get(CONSENT_COOKIE) in ("yes", "no") and st.session_state.get("consent") is None:
            st.session_state["consent"] = _all[CONSENT_COOKIE]
        _saved = "".join(ch for ch in str(_all.get(VID_COOKIE) or "") if ch.isalnum())[:32]
        if _all.get(CONSENT_COOKIE) == "yes" and _saved and _saved != st.session_state["visitor"]:
            st.session_state["visitor"] = _saved
            try:
                st.query_params["v"] = _saved
            except Exception:
                pass


def _write_consent_cookies() -> None:
    if not _cookie_manager:
        return
    from datetime import timedelta
    expires = datetime.now() + timedelta(days=365)
    try:
        for name, value, k in ((CONSENT_COOKIE, st.session_state["consent"], "set_ur_consent"),
                               (VID_COOKIE, st.session_state["visitor"], "set_ur_vid")):
            if name == VID_COOKIE and st.session_state["consent"] != "yes":
                continue
            try:  # whole-site cookie, so the server sees it on the next visit
                _cookie_manager.set(name, value, expires_at=expires, key=k, path="/", same_site="lax")
            except TypeError:  # older library without path/same_site arguments
                _cookie_manager.set(name, value, expires_at=expires, key=k)
    except Exception:
        pass


if st.session_state.pop("write_cookies", False):
    _write_consent_cookies()

st.session_state["ck_runs"] = st.session_state.get("ck_runs", 0) + 1
# wait until the cookie component has reported (or ~2 runs), so returning visitors never see a flash
_ready = (not _cookie_manager) or st.session_state.get("cookie_checked") or st.session_state["ck_runs"] >= 3
if st.session_state.get("consent") is None and _ready:
    try:
        _banner = st.container(key="consent")
    except TypeError:
        _banner = st.container()
    with _banner:
        st.markdown('<div class="ck-title">Cookies</div><div class="ck-text">We use one functional cookie to remember '
                    'your anonymous ID, so you can see your own cases when you come back. No tracking, no ads, '
                    'no personal data.</div>', unsafe_allow_html=True)
        _a, _b = st.columns(2)
        if _a.button("Accept", key="ck_yes", type="primary", use_container_width=True):
            st.session_state["consent"] = "yes"
            st.session_state["write_cookies"] = True
            st.rerun()
        if _b.button("Only this session", key="ck_no", use_container_width=True):
            st.session_state["consent"] = "no"
            st.session_state["write_cookies"] = True
            st.rerun()
VISITOR = st.session_state["visitor"]

import inspect  # noqa: E402
# tolerate a backend module that is older than this page (e.g. hosting kept the old one in memory)
OWNER_KW = {"owner": VISITOR} if "owner" in inspect.signature(process_ticket).parameters else {}
HISTORY_HAS_OWNER = "owner" in inspect.signature(get_ticket_history).parameters
LOGO = HERE / "logo.svg"
ICON = HERE / "icon.svg"
try:
    st.logo(str(LOGO), size="large", icon_image=str(ICON))
except Exception:
    pass

def header(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="page"><div class="kicker">UniResolve AI</div><div class="page-h">{e(title)}</div>'
                f'<div class="hero-p">{e(subtitle)}</div></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- pages
def page_resolve() -> None:
    st.markdown(f'''<div class="hero-wrap"><div>
<span class="hero-k"><span class="live-dot"></span> 6 AI agents · auditor-verified · any language</span>
<span class="heritage">{BOOK_SVG} Debrecen · since 1538</span>
<div class="hero-h">Campus problems,<br><span class="grad">resolved by agents.</span></div>
<div class="hero-p">Describe what went wrong. UniResolve classifies it, finds the office that owns it, writes a plan,
has an independent auditor check it, and drafts the message you can send.</div></div>
<div>{SKYLINE_SVG}</div></div>''', unsafe_allow_html=True)
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    if "problem" not in st.session_state:
        st.session_state["problem"] = ""

    def use_example(text: str) -> None:
        st.session_state["problem"] = text

    st.text_area("Your problem", key="problem", height=120, label_visibility="collapsed",
                 placeholder="e.g. The Wi-Fi in the library is down and my exam starts in an hour.")
    c1, c2, c3 = st.columns([1.3, 1, 1])
    cat = c1.selectbox("Category · optional", CATEGORIES)
    custom_cat = ""
    if cat == "other":
        custom_cat = c1.text_input("Describe the category", placeholder="e.g. sports club, parking permit…",
                                   key="custom_cat")
    urg = c2.selectbox("Urgency · optional", ["(let the agents decide)", "low", "medium", "high", "critical"])
    c3.markdown("<div style='height:27px'></div>", unsafe_allow_html=True)
    go = c3.button("Resolve with agents  →", type="primary", use_container_width=True)
    st.markdown('<div class="kicker" style="margin:14px 0 8px">Try an example</div>', unsafe_allow_html=True)
    ex_cols = st.columns(len(EXAMPLES))
    for col, ex in zip(ex_cols, EXAMPLES):
        col.button(ex[:40] + ("…" if len(ex) > 40 else ""), on_click=use_example, args=(ex,),
                   use_container_width=True, help=ex)

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    inc_go = st.button("Simulate a campus incident · 3 students report the same outage", use_container_width=True,
                       help="Sends three real reports about the library Wi-Fi one after another. "
                            "On the third, the Incident Agent groups them into one campus incident.")
    if inc_go:
        reports = ["The Wi-Fi is down in the main library",
                   "No internet in the library since 10 minutes, eduroam fails",
                   "Eduroam not working at the library, I cannot connect at all"]
        last = None
        for i, text in enumerate(reports, 1):
            st.markdown(f'<div class="section">Report {i} of 3 · “{e(text)}”</div>', unsafe_allow_html=True)
            pipe_ph = st.empty()
            pipe_ph.markdown(render_pipeline([]), unsafe_allow_html=True)
            tl_ph = st.empty()
            last = process_ticket(text, mode=mode, on_event=live_runner(pipe_ph, tl_ph), **OWNER_KW)
            pipe_ph.markdown(render_pipeline(last.get("execution_trace") or [], finished=True), unsafe_allow_html=True)
            tl_ph.empty()
        st.session_state["last_result"] = last
        st.rerun()

    if go:
        text = st.session_state["problem"].strip()
        if not text:
            st.warning("Please describe a problem first.")
        else:
            st.markdown('<div class="section">Agents at work</div>', unsafe_allow_html=True)
            pipe_ph = st.empty()
            pipe_ph.markdown(render_pipeline([]), unsafe_allow_html=True)
            tl_ph = st.empty()
            chosen = (custom_cat.strip() or "other") if cat == "other" else (None if cat.startswith("(") else cat)
            result = process_ticket(text, category=chosen,
                                    urgency=None if urg.startswith("(") else urg, mode=mode,
                                    on_event=live_runner(pipe_ph, tl_ph), **OWNER_KW)
            st.session_state["last_result"] = result
            st.rerun()

    if st.session_state.get("last_result"):
        r = st.session_state["last_result"]
        st.markdown('<div class="section">Agent pipeline</div>', unsafe_allow_html=True)
        st.markdown(render_pipeline(r.get("execution_trace") or [], finished=True), unsafe_allow_html=True)
        render_result(r)
    else:
        st.markdown(ORNAMENT, unsafe_allow_html=True)
        st.markdown('<div class="reveal"><div class="kicker">How it works</div>'
                    '<div class="bigq" style="margin:10px 0 26px">Six agents that check each other\'s work, '
                    '<span class="grad">and know when to ask a human.</span></div></div>', unsafe_allow_html=True)
        feats = [
            ("T", "Triage", "Reads the message in any language: category, urgency, exam, safety risk, location."),
            ("I", "Incident detection", "Three students, one library, one outage? It merges them into a campus incident."),
            ("R", "Routing", "Finds the office that owns the problem and decides if a staff decision is needed."),
            ("P", "Resolution", "Writes a step-by-step plan grounded in the knowledge base, using lessons from past mistakes."),
            ("A", "Auditor", "Eight code checks plus an independent LLM review. Weak plans are rejected and revised."),
            ("C", "Communication", "Drafts the message to the right office, with no invented contacts or actions."),
        ]
        st.markdown('<div class="feats">' + "".join(
            f'<div class="feat"><div class="fi">{a}</div><h3>{e(t)}</h3><p>{e(d)}</p></div>' for a, t, d in feats)
            + '</div>', unsafe_allow_html=True)
        st.markdown(ORNAMENT, unsafe_allow_html=True)
        st.markdown('<div class="reveal"><div class="kicker">Measured, not promised</div>'
                    '<div class="bigq" style="margin:10px 0 22px">Evaluated on 20 hand-labelled student problems.</div></div>',
                    unsafe_allow_html=True)
        stats = [("100%", "routing accuracy"), ("17/20", "accepted by the auditor first time"),
                 ("2.8 s", "median time per case"), ("108/108", "LLM calls answered live")]
        st.markdown('<div class="stats">' + "".join(
            f'<div class="stat"><div class="v">{v}</div><div class="l">{e(l)}</div></div>' for v, l in stats)
            + '</div>', unsafe_allow_html=True)
        st.markdown('<div class="small" style="margin-top:10px">Small hand-made test set, live LLM run at 14:35 '
                    '(demo/evaluate.py). Numbers describe that run, not real-world performance.</div>',
                    unsafe_allow_html=True)

def page_dashboard() -> None:
    header("Campus support at a glance", "Live numbers counted from every stored case.")
    s = get_dashboard_stats()
    cols = st.columns(5)
    cols[0].metric("Cases processed", s["total_tickets"])
    cols[1].metric("Verified plans", s["verified_solutions"])
    cols[2].metric("Waiting for staff", s["pending_human_approval"])
    cols[3].metric("Open incidents", s.get("open_incidents") or 0)
    avg = s.get("avg_processing_time_ms")
    cols[4].metric("Avg. time per case", f"{avg / 1000:.1f} s" if avg else "-")

    st.markdown('<div class="section">Active campus incidents</div>', unsafe_allow_html=True)
    incs = get_incidents()
    if not incs:
        st.markdown('<div class="card small">No open incidents. When 3+ students report the same problem in the '
                    'same place within an hour, the Incident Agent groups them here.</div>', unsafe_allow_html=True)
    for inc in incs:
        a, b = st.columns([5, 1])
        a.markdown(f'''<div class="card"><div class="tl-head"><div><div class="kicker">{e(inc["incident_id"])}</div>
<div style="font-family:'Space Grotesk',sans-serif;font-size:1.2rem">{e(inc["title"])}</div>
<div class="small">{e(inc["location"])} · owner {e(inc["department"])} · since {fmt_time(inc["created_at"])}</div></div>
<div>{pill(f'{inc["report_count"]} reports', "gold")}</div></div></div>''', unsafe_allow_html=True)
        if b.button("Close", key=f"close_{inc['incident_id']}", use_container_width=True):
            close_incident(inc["incident_id"])
            st.rerun()

    an = get_analytics()
    if an["total_cases"]:
        st.markdown('<div class="section">Where students need help</div>', unsafe_allow_html=True)
        g1, g2 = st.columns(2)
        with g1:
            st.markdown('<div class="kicker">By category</div>', unsafe_allow_html=True)
            st.bar_chart(pd.DataFrame({"cases": an["by_category"]}), color=GOLD, height=260)
        with g2:
            st.markdown('<div class="kicker">By department</div>', unsafe_allow_html=True)
            st.bar_chart(pd.DataFrame({"cases": an["by_department"]}), color="#5FB98C", height=260)
        g3, g4 = st.columns(2)
        with g3:
            st.markdown('<div class="kicker">What the auditor catches most</div>', unsafe_allow_html=True)
            if an["auditor_failed_checks"]:
                st.bar_chart(pd.DataFrame({"rejections": an["auditor_failed_checks"]}), color=REJECT, height=240)
            else:
                st.markdown('<div class="small">No rejections yet.</div>', unsafe_allow_html=True)
        with g4:
            st.markdown('<div class="kicker">What the system learned</div>', unsafe_allow_html=True)
            L = get_lessons_learned()
            for c in L.get("student_feedback") or []:
                st.markdown(f'<div class="step"><div class="stepn">S</div><div>{e(c)}'
                            f'<div class="meta">student feedback · now fed into new plans</div></div></div>',
                            unsafe_allow_html=True)
            if L["lessons"]:
                st.markdown("".join(
                    f'<div class="step"><div class="stepn">{x["seen_overall"]}</div><div>{e(x["lesson"])}'
                    f'<div class="meta">{e(x["check"])} · rejected {x["seen_overall"]}x before, now fed into every new plan</div></div></div>'
                    for x in L["lessons"]), unsafe_allow_html=True)
            elif not L.get("student_feedback"):
                st.markdown('<div class="small">Nothing learned yet.</div>', unsafe_allow_html=True)
        if an["top_locations"]:
            st.markdown('<div class="kicker" style="margin-top:12px">Hotspots</div>', unsafe_allow_html=True)
            st.markdown(" ".join(pill(f"{k} · {v}", "gold") for k, v in an["top_locations"].items()),
                        unsafe_allow_html=True)

def page_staff() -> None:
    header("Staff review", "Cases the agents will not decide alone: policy decisions and escalations.")
    pending = get_pending_reviews()
    if not pending:
        st.markdown('<div class="card small">Nothing waiting for a decision.</div>', unsafe_allow_html=True)
    for t in pending:
        label, kind = STATUS_TEXT.get(t["status"], (t["status"], ""))
        with st.expander(f'{t["ticket_id"]} · {t["original_input"][:80]}'):
            full = get_ticket(t["ticket_id"]) or {}
            fs = full.get("final_solution") or {}
            st.markdown(f'{pill(label, kind)} {pill(t["assigned_department"] or "-")} {pill(t["priority"] or "-")}',
                        unsafe_allow_html=True)
            st.markdown("".join(f'<div class="step"><div class="stepn">{i}</div><div>{e(s["action"])}</div></div>'
                                for i, s in enumerate(fs.get("steps") or [], 1)), unsafe_allow_html=True)
            reviewer = st.text_input("Reviewer", value="Study Office staff", key=f"rv_{t['ticket_id']}")
            note = st.text_input("Note", key=f"nt_{t['ticket_id']}", placeholder="e.g. medical certificate received")
            a, b = st.columns(2)
            if a.button("Approve", type="primary", key=f"ap_{t['ticket_id']}", use_container_width=True):
                review_ticket(t["ticket_id"], "approve", reviewer, note)
                st.toast("Approved")
                st.rerun()
            if b.button("Reject", key=f"rj_{t['ticket_id']}", use_container_width=True):
                review_ticket(t["ticket_id"], "reject", reviewer, note)
                st.toast("Rejected")
                st.rerun()

def page_history() -> None:
    header("Case history", "Your cases, with the full trace of what each agent did. "
           "Accept the cookie to keep them when you come back.")
    mine = "My cases" if st.session_state.get("consent") == "yes" else "This session"
    scope = st.radio("Show", [mine, "All cases (staff view)"], horizontal=True,
                     label_visibility="collapsed", key="hist_scope")
    if HISTORY_HAS_OWNER:
        hist = get_ticket_history(owner=VISITOR if scope == mine else None)
    else:
        hist = get_ticket_history()
    if not hist:
        st.markdown('<div class="card small">No cases yet. Describe a problem on the Resolve page; '
                    'it appears here, visible only to you. Staff can see every case in "All cases".</div>',
                    unsafe_allow_html=True)
    else:
        df = pd.DataFrame(hist)[["ticket_id", "created_at", "original_input", "category", "priority",
                                 "assigned_department", "status", "revision_count", "execution_mode"]]
        df["created_at"] = df["created_at"].map(fmt_time)
        st.dataframe(df, use_container_width=True, hide_index=True, height=300)
        pick = st.selectbox("Open a case", [h["ticket_id"] for h in hist],
                            format_func=lambda i: f'{i} · {next(h["original_input"][:70] for h in hist if h["ticket_id"] == i)}')
        if pick:
            r = get_ticket(pick)
            st.markdown('<div class="section">Agent activity</div>', unsafe_allow_html=True)
            st.markdown(render_timeline(r.get("execution_trace") or []), unsafe_allow_html=True)
            render_result(r)

def page_backup() -> None:
    header("Recorded live runs", "If the network fails during the pitch: real runs recorded earlier, replayed step by step.")
    runs = get_recorded_runs()
    if not runs:
        st.markdown('<div class="card small">No recorded runs in demo/recorded_runs/.</div>', unsafe_allow_html=True)
    else:
        pick = st.selectbox("Recorded run", [x["ticket_id"] for x in runs],
                            format_func=lambda i: next(f'{x["original_input"][:70]} · {x["status"]}' for x in runs if x["ticket_id"] == i))
        if st.button("Replay", type="primary"):
            st.markdown('<div class="banner rec">RECORDED RUN · replaying a real live run from the log</div>',
                        unsafe_allow_html=True)
            pipe_ph, tl_ph = st.empty(), st.empty()
            pipe_ph.markdown(render_pipeline([]), unsafe_allow_html=True)
            r = replay_ticket(pick, on_event=live_runner(pipe_ph, tl_ph), speed=1.0)
            pipe_ph.markdown(render_pipeline(r.get("execution_trace") or [], finished=True), unsafe_allow_html=True)
            render_result(r, recorded=True)



def controls() -> str:
    """Live/offline switch + model status, top right of every page. Returns the execution mode."""
    try:
        box = st.container(key="ctrl")
    except TypeError:
        box = st.container()
    with box:
        return _controls_inner()


def _controls_inner() -> str:
    _, c1, c2 = st.columns([6.2, 1.1, 1.3], vertical_alignment="center")
    live = c1.toggle("Live AI", value=st.session_state.get("live", True), key="live",
                     help="Off = clearly labelled offline simulation (no API calls).")
    any_ready = any(p["ready"] for p in status["providers"].values())
    n_models = sum(len(p.get("models") or []) for p in status["providers"].values())
    with c2.popover(f"{'●' if any_ready else '○'}  {n_models} models", use_container_width=True):
        st.markdown('<div class="kicker">AI engine</div>', unsafe_allow_html=True)
        for name, p in status["providers"].items():
            st.markdown(f'<div class="small" style="margin:6px 0"><span class="dot {"" if p["ready"] else "off"}"></span>&nbsp; '
                        f'<b>{name}</b> · {", ".join(e(m) for m in (p.get("models") or []))}</div>', unsafe_allow_html=True)
        if st.button("Run health check", use_container_width=True):
            st.session_state["health"] = check_models()
        for h in st.session_state.get("health") or []:
            ok = h["status"] == "ok"
            st.markdown(f'<div class="meta"><span class="dot {"" if ok else "off"}"></span>&nbsp; {e(h["model"])} · '
                        f'{h["latency_ms"]} ms{"" if ok else " · busy"}</div>', unsafe_allow_html=True)
    if not live:
        st.markdown('<div class="banner sim">OFFLINE SIMULATION MODE · agents use deterministic mock outputs, '
                    'no AI is called</div>', unsafe_allow_html=True)
    return "auto" if live else "offline"


def footer_bar() -> None:
    st.markdown('<div class="footer"><span>UniResolve AI · Team Caucasus · GDG Debrecen Agentic AI Hackathon 2026</span>'
                '<span>Made in Debrecen · Cívisváros · demo data, not official university information</span></div>', unsafe_allow_html=True)


PAGE_LIST = [(page_resolve, "Resolve", "resolve"), (page_dashboard, "Dashboard", "dashboard"),
             (page_staff, "Staff review", "staff"), (page_history, "History", "history"),
             (page_backup, "Backup demo", "backup")]


def _wrap(fn):
    def run() -> None:
        global mode
        try:
            box = st.container(key=f"pg_{fn.__name__}")
        except TypeError:  # very old Streamlit: no keyed containers
            box = st.container()
        with box:
            mode = controls()
            fn()
            footer_bar()
    run.__name__ = fn.__name__
    return run


mode = "auto"
try:
    nav = st.navigation([st.Page(_wrap(fn), title=t, url_path=u, default=(u == "resolve")) for fn, t, u in PAGE_LIST],
                        position="top")
except TypeError:  # older Streamlit without top navigation: simple fallback menu
    nav = None
if nav is not None:
    nav.run()
else:
    choice = st.radio("Navigate", [t for _, t, _ in PAGE_LIST], horizontal=True, label_visibility="collapsed")
    _wrap(next(fn for fn, t, _ in PAGE_LIST if t == choice))()
