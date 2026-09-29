import re
import json
from pathlib import Path

html = Path(__file__).with_name("surebets_page.html").read_text(encoding="utf-8")
out = {}

block = re.search(r'id="filter_current_id".*?</select>', html, re.S)
out["filters"] = []
if block:
    for v, t in re.findall(r'<option[^>]*value="([^"]+)"[^>]*>([^<]*)</option>', block.group(0)):
        out["filters"].append({"id": v, "name": t.strip(), "selected": "selected" in (re.search(rf'value="{re.escape(v)}"[^>]*>', block.group(0)) or type("", (), {"group": lambda s: ""})()).group(0)})

# better selected detection
if block:
    out["filters"] = []
    for m in re.finditer(r'<option([^>]*)value="([^"]+)"([^>]*)>([^<]*)</option>', block.group(0)):
        pre, val, post, text = m.group(1), m.group(2), m.group(3), m.group(4).strip()
        out["filters"].append({
            "id": val,
            "name": text,
            "selected": "selected" in pre or "selected" in post,
        })

tables = re.findall(r'<table([^>]*)id="([^"]*)"([^>]*)>', html)
out["tables"] = [{"id": t[1], "attrs": (t[0] + t[2])[:300]} for t in tables]

attrs = re.findall(r'<tbody class="([^"]*record[^"]*)"([^>]*)>', html)
out["record_classes"] = sorted(set(a[0] for a in attrs))
out["record_count"] = len(attrs)
out["first_record_attrs"] = (attrs[0][0] + " " + attrs[0][1])[:500] if attrs else None

# also try surebet_record specifically
recs = re.findall(r'<tbody class="surebet_record"[^>]*>', html)
out["surebet_record_count"] = len(recs)
if not attrs:
    # try data-product-model
    attrs2 = re.findall(r'<tbody([^>]*data-product-model="surebet"[^>]*)>', html)
    out["surebet_tbody_count"] = len(attrs2)
    if attrs2:
        out["first_record_attrs"] = attrs2[0][:500]

m = re.search(r'<tbody class="[^"]*record[^"]*".*?</tbody>', html, re.S)
if not m:
    m = re.search(r'<tbody[^>]*data-product-model="surebet"[^>]*>.*?</tbody>', html, re.S)
if m:
    chunk = m.group(0)
    Path(__file__).with_name("surebet_sample_record.html").write_text(chunk, encoding="utf-8")
    out["testids"] = sorted(set(re.findall(r'data-testid="([^"]+)"', chunk)))
    out["data_attrs"] = re.findall(r'(data-[a-z0-9-]+)="([^"]*)"', re.search(r'<tbody[^>]*>', chunk).group(0)) if re.search(r'<tbody[^>]*>', chunk) else []
    out["profit_text"] = re.findall(r'class="[^"]*profit[^"]*"[^>]*>([^<]+)', chunk)[:5]
    out["odds"] = re.findall(r'data-testid="record-card-leg-odds"[^>]*>([^<]+)', chunk)[:6]
    out["bookies"] = re.findall(r'data-testid="record-card-leg-bookmaker"[^>]*>([^<]+)', chunk)[:6]
    out["markets"] = re.findall(r'data-testid="record-card-leg-market"[^>]*>([^<]+)', chunk)[:6]

# min profit input
mo = re.search(r'id="selector_min_profit"[^>]*value="([^"]*)"', html)
out["min_profit_input"] = mo.group(1) if mo else None

Path(__file__).with_name("surebets_dom_summary.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("ok")
