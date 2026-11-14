"""Global CSS for the official-style look."""

CSS = """
<style>
#MainMenu, footer, header [data-testid="stToolbar"] {visibility: hidden;}
/* hide the "Press Enter to apply" hint under inputs */
[data-testid="InputInstructions"] {display: none !important;}

.block-container {padding-top: 0.5rem; max-width: 1180px;}
html, body, [class*="css"] {font-family: "Segoe UI", Roboto, Arial, sans-serif;}

/* tricolour strip + header */
.tricolor {height: 6px; background: linear-gradient(90deg,#FF9933 33%,#FFFFFF 33% 66%,#138808 66%);
           border: 1px solid #e5e7eb; border-radius: 3px; margin-bottom: .6rem;}
.gov-top {background:#0B2A6F; color:#fff; padding:.45rem 1rem; border-radius:8px 8px 0 0;
          font-size:.82rem; display:flex; justify-content:space-between; flex-wrap:wrap; gap:.5rem;}
.gov-header {background:#fff; border:1px solid #dbe2f0; border-top:none; padding:1rem 1.4rem;
             border-radius:0 0 8px 8px; display:flex; align-items:center; gap:1rem; margin-bottom:1rem;}
.gov-header .logo {font-size:2.4rem;}
.gov-header h1 {margin:0; color:#0B2A6F; font-size:1.8rem; letter-spacing:.2px;}
.gov-header p {margin:.15rem 0 0 0; color:#4b5563; font-size:.95rem;}
.notice {background:#FFF8E6; border-left:4px solid #FF9933; padding:.6rem .9rem; border-radius:6px;
         font-size:.88rem; color:#7a4b00; margin-bottom:1rem;}

/* section headings */
h2, h3 {color:#0B2A6F;}
.section-title {color:#0B2A6F; font-weight:700; font-size:1.15rem; border-bottom:3px solid #FF9933;
                display:inline-block; padding-bottom:.15rem; margin:.6rem 0 .6rem 0;}

/* scheme cards */
[data-testid="stVerticalBlockBorderWrapper"] {background:#fff; border-radius:10px;
        border-color:#dbe2f0 !important; box-shadow:0 1px 4px rgba(11,42,111,.08);}
.badge {display:inline-block; padding:.2rem .7rem; border-radius:999px; color:#fff;
        font-weight:600; font-size:.82rem; margin-right:.4rem;}
.tag {display:inline-block; padding:.15rem .6rem; border-radius:6px; background:#EEF2FF; color:#0B2A6F;
      font-size:.8rem; margin-right:.3rem; border:1px solid #dbe2f0;}
.fact-label {color:#6b7280; font-size:.78rem; text-transform:uppercase; letter-spacing:.4px;}
.fact-value {color:#111827; font-size:.95rem; margin-bottom:.4rem;}
.unverified {color:#b45309; font-weight:600;}

/* buttons */
.stButton > button, .stLinkButton > a {border-radius:8px; font-weight:600; padding:.55rem 1rem;}
.stButton > button[kind="secondary"] {border:2px solid #0B2A6F; color:#0B2A6F; background:#fff;}
.stButton > button[kind="secondary"]:hover {background:#0B2A6F; color:#fff;}
.stButton > button[kind="primary"] {background:#138808; border:2px solid #138808; color:#fff;}
.stButton > button[kind="primary"]:hover {background:#0e6b06; border-color:#0e6b06;}

/* sidebar */
[data-testid="stSidebar"] {background:#fff; border-right:1px solid #dbe2f0;}
.footer-note {text-align:center; color:#6b7280; font-size:.8rem; margin-top:2rem;}
</style>
"""

HEADER_HTML = """
<div class="tricolor"></div>
<div class="gov-top"><span>🇮🇳 Citizen Information Assistant for Indian Government Schemes</span>
<span>Independent tool - not an official Government of India website</span></div>
<div class="gov-header"><div class="logo">🏛️</div>
<div><h1>SchemeFinder AI</h1>
<p>Find schemes, check eligibility and apply through official portals - with sources for every answer.</p></div></div>
"""

NOTICE_HTML = """<div class="notice"><b>Please note:</b> This tool does not approve or submit applications.
Always confirm eligibility, deadlines and links on the official government portal before applying.</div>"""
