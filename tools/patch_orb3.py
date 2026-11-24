#!/usr/bin/env python3
"""One-off patch 3: extra orb effects (aura, spinning rings with dots, ripples, sparks). UI only."""
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
p = REPO / "sentinel_v2.html"
s = p.read_text(encoding="utf-8")
shutil.copy2(p, REPO / "backups" / "sentinel_v2.html.bak-orb-effects")

CSS = """#orbwrap{position:relative;width:min(46vmin,280px);aspect-ratio:1;--o:var(--mode,var(--accent));}
.orb-aura{position:absolute;inset:-35%;border-radius:50%;background:radial-gradient(circle,var(--o) 0%,transparent 65%);opacity:0.12;filter:blur(18px);pointer-events:none;transition:opacity 0.4s;}
#orbview.talk .orb-aura{opacity:calc(0.25 + var(--lv,0)*0.4);transform:scale(calc(1 + var(--lv,0)*0.2));transition:transform 0.1s linear,opacity 0.1s linear;}
.orb-ring{position:absolute;border-radius:50%;pointer-events:none;transition:opacity 0.5s;}
.orb-r1{inset:-14%;border:1px dashed color-mix(in srgb,var(--o) 60%,transparent);opacity:0.45;animation:orbSpin 28s linear infinite;}
.orb-r2{inset:-27%;border:1px solid color-mix(in srgb,var(--o) 30%,transparent);opacity:0.4;animation:orbSpin 46s linear infinite reverse;}
#orbview.talk .orb-r1{opacity:0.85;animation-duration:9s;}
#orbview.talk .orb-r2{opacity:0.75;animation-duration:16s;}
.orb-dot{position:absolute;width:7px;height:7px;border-radius:50%;background:var(--o);box-shadow:0 0 10px var(--o);left:calc(50% - 3px);top:-3px;}
.orb-r2 .orb-dot{top:auto;bottom:-3px;width:5px;height:5px;left:calc(50% - 2px);}
.orb-ripple{position:absolute;inset:0;border-radius:50%;border:2px solid var(--o);opacity:0;pointer-events:none;}
#orbview.talk .orb-ripple{animation:orbRipple 2.4s ease-out infinite;}
#orbview.talk .orb-ripple.rp2{animation-delay:0.8s;}
#orbview.talk .orb-ripple.rp3{animation-delay:1.6s;}
.orb-spark{position:absolute;left:var(--x);top:55%;width:4px;height:4px;border-radius:50%;background:var(--o);box-shadow:0 0 8px var(--o);opacity:0;pointer-events:none;}
#orbview.talk .orb-spark{animation:orbFloat 3.6s ease-in infinite;animation-delay:var(--d);}
@keyframes orbSpin{to{transform:rotate(360deg)}}
@keyframes orbRipple{0%{transform:scale(1);opacity:0.55}100%{transform:scale(1.9);opacity:0}}
@keyframes orbFloat{0%{transform:translateY(0);opacity:0}15%{opacity:0.9}100%{transform:translateY(-150px);opacity:0}}
"""

SPARKS = "".join(
    f'<i class="orb-spark" style="--x:{x}%;--d:{d}s"></i>'
    for x, d in [(8, 0), (24, 1.1), (40, 2.2), (60, 0.6), (76, 1.7), (92, 2.8)]
)

HTML_NEW = ('<div id="orbview"><div id="orbwrap"><div class="orb-aura"></div>'
            '<div class="orb-ripple"></div><div class="orb-ripple rp2"></div><div class="orb-ripple rp3"></div>'
            '<div class="orb-ring orb-r1"><i class="orb-dot"></i></div><div class="orb-ring orb-r2"><i class="orb-dot"></i></div>'
            '<div id="orb"></div>' + SPARKS + '</div><div id="orb-lb">quiet</div></div>')

edits = [
    ("</style>", CSS + "</style>"),
    ("width:min(46vmin,280px);aspect-ratio:1;border-radius:50%;background:radial-gradient",
     "position:absolute;inset:0;border-radius:50%;background:radial-gradient"),
    ('<div id="orbview"><div id="orb"></div><div id="orb-lb">quiet</div></div>', HTML_NEW),
    ("  if(on) document.getElementById('orb').style.setProperty('--lv',lv||0);\n",
     "  if(on) document.getElementById('orbview').style.setProperty('--lv',lv||0);\n"),
    ("  document.getElementById('orb').classList.toggle('talk',on);\n",
     "  document.getElementById('orb').classList.toggle('talk',on);\n  document.getElementById('orbview').classList.toggle('talk',on);\n"),
]
for old, new in edits:
    n = s.count(old)
    assert n == 1, f"anchor matched {n} times: {old[:60]!r}"
    s = s.replace(old, new)
p.write_text(s, encoding="utf-8")
print("patched sentinel_v2.html")
