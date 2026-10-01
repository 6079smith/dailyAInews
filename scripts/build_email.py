#!/usr/bin/env python3
"""Render site/data/news.json into a phone-friendly HTML email (site/email.html)
and optionally send it over SMTP.

Config: config/email.json  ("sources": "default" | "all" | ["openai", ...]).
Send:   set SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASS, EMAIL_TO [, EMAIL_FROM].
Without SMTP_HOST it only writes the preview file.
"""
import json, os, smtplib, ssl, sys
from datetime import datetime
from email.message import EmailMessage
from html import escape as e
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
cfg = json.loads((ROOT / "config" / "email.json").read_text())
data = json.loads((ROOT / "site" / "data" / "news.json").read_text())
names = {s["id"]: s["name"] for s in data["sources"]}
if cfg["sources"] == "all":
    allowed = set(names)
elif cfg["sources"] == "default":
    allowed = {s["id"] for s in data["sources"] if s["default"]}
else:
    allowed = set(cfg["sources"])

stories = []
for s in data["stories"]:
    arts = sorted((a for a in s["articles"] if a["source"] in allowed), key=lambda a: -a["score"])
    if arts:
        stories.append((s["category"], arts[0]["score"] + 0.6 * (len(arts) - 1), arts))
stories.sort(key=lambda x: -x[1])

picked, per = [], {}
for cat, sc, arts in stories:
    if len(picked) >= cfg["max_stories"]:
        break
    if per.get(cat, 0) >= cfg["max_per_category"]:
        continue
    per[cat] = per.get(cat, 0) + 1
    picked.append((cat, arts))

date = datetime.now().strftime("%A %-d %B")
parts = [f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f6f7f9;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#14171c">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:12px">
<table role="presentation" width="100%" style="max-width:560px" cellpadding="0" cellspacing="0">
<tr><td style="padding:8px 4px 14px"><div style="font-size:22px;font-weight:700">{e(cfg["subject"])}</div><div style="font-size:13px;color:#5d6674">{e(date)} · free-to-read sources only</div></td></tr>''']
for cat in dict.fromkeys(c for c, _ in picked):
    parts.append(f'<tr><td style="padding:14px 4px 6px;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#5d6674">{e(cat)}</td></tr>')
    for c, arts in picked:
        if c != cat:
            continue
        lead = arts[0]
        also = " · ".join(f'<a href="{e(a["url"])}" style="color:#3b5bdb;text-decoration:none">{e(names[a["source"]])}</a>' for a in arts[1:4])
        parts.append(f'''<tr><td style="padding:0 0 10px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fff;border:1px solid #e3e6eb;border-radius:12px"><tr><td style="padding:14px">
<div style="font-size:12px;color:#5d6674"><b style="color:#14171c">{e(names[lead["source"]])}</b></div>
<a href="{e(lead["url"])}" style="display:block;margin:4px 0 6px;font-size:17px;line-height:1.3;font-weight:600;color:#14171c;text-decoration:none">{e(lead["title"])}</a>
<div style="font-size:14px;line-height:1.45;color:#5d6674">{e(lead["snippet"])}</div>
{f'<div style="margin-top:8px;font-size:12.5px;color:#5d6674">Also: {also}</div>' if also else ""}
</td></tr></table></td></tr>''')
if cfg.get("site_url"):
    parts.append(f'<tr><td align="center" style="padding:10px;font-size:13px"><a href="{e(cfg["site_url"])}" style="color:#3b5bdb">Open the full dashboard</a></td></tr>')
parts.append("</table></td></tr></table></body></html>")
html = "".join(parts)
(ROOT / "site" / "email.html").write_text(html)
print(f"email.html written: {len(picked)} stories")

if os.environ.get("SMTP_HOST"):
    if not picked:
        print("no stories; not sending"); sys.exit(0)
    msg = EmailMessage()
    msg["Subject"] = f'{cfg["subject"]} – {date}'
    msg["From"] = os.environ.get("EMAIL_FROM", os.environ["SMTP_USER"])
    msg["To"] = os.environ["EMAIL_TO"]
    msg.set_content("\n\n".join(f'[{c}] {a[0]["title"]}\n{a[0]["url"]}' for c, a in picked))
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587))) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)
    print("sent to", os.environ["EMAIL_TO"])
