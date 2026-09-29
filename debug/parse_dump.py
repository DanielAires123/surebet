import re
import json
from pathlib import Path

html = Path(__file__).with_name("valuebets_page.html").read_text(encoding="utf-8")
out = {}

block = re.search(r'id="filter_current_id".*?</select>', html, re.S)
out["filters"] = []
if block:
    for v, t in re.findall(r'<option[^>]*value="([^"]+)"[^>]*>([^<]*)</option>', block.group(0)):
        out["filters"].append({"id": v, "name": t.strip()})

attrs = re.findall(r'<tbody class="valuebet_record"([^>]*)>', html)
out["record_count"] = len(attrs)
out["first_record_attrs"] = attrs[0].strip() if attrs else None

m = re.search(r'<tbody class="valuebet_record".*?</tbody>', html, re.S)
if m:
    chunk = m.group(0)
    Path(__file__).with_name("sample_record.html").write_text(chunk, encoding="utf-8")
    out["testids"] = sorted(set(re.findall(r'data-testid="([^"]+)"', chunk)))
    out["overvalue_text"] = re.findall(r'class="overvalue"[^>]*>([^<]+)', chunk)[:3]
    out["bookie_hrefs"] = re.findall(r'/nav/bookie/([^"\']+)', chunk)[:3]
    out["prong_ids"] = re.findall(r'/nav/valuebet/prong/([^/"\']+)', chunk)[:3]
    out["odds_test"] = re.findall(
        r'data-testid="record-card-leg-odds"[^>]*>([^<]+)', chunk
    )[:3]

Path(__file__).with_name("dom_summary.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("wrote dom_summary.json")
