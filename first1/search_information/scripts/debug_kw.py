#!/usr/bin/env python3
"""Debug: show all keyword groups loaded"""
import re, sqlite3, sys

kw_path = "/root/projects/search_information/search_information/TrendRadar/config/frequency_words.txt"
groups = {}
current = None
with open(kw_path) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and "] " in line:
            name = line.split("]")[0].lstrip("[").strip()
            current = name
            groups[current] = {"kws": [], "level": "⚪"}
            if "⭐" in line: groups[current]["level"] = "🔴"
            elif "📁" in line: groups[current]["level"] = "🟡"
        elif current and "/" in line:
            kws = [k.strip() for k in line.split("/") if k.strip()]
            for kw in kws:
                if kw.startswith("\\b") or kw.startswith("\\"):
                    # Keep regex keywords as-is
                    groups[current]["kws"].append(kw.lstrip("\\"))
                elif kw.startswith("=>"):
                    continue
                elif len(kw) >= 2:
                    groups[current]["kws"].append(kw)

print("Total groups: %d" % len(groups))
for g, d in sorted(groups.items(), key=lambda x: -len(x[1]["kws"])):
    print("  %s %s: %d kws" % (d["level"], g, len(d["kws"])))
    if d["kws"]:
        print("    first:", d["kws"][:3])

# Test matching on real data
conn = sqlite3.connect("/root/projects/data/search_information/news/2026-06-03.db")
titles = [r[0] for r in conn.execute("SELECT title FROM news_items").fetchall()]
conn.close()

print("\n=== Match results ===")
for g, d in sorted(groups.items(), key=lambda x: -len(x[1]["kws"])):
    if not d["kws"]:
        continue
    hits = 0
    titles_sample = []
    for kw in d["kws"]:
        if len(kw) < 2:
            continue
        try:
            pat = re.compile(re.escape(kw), re.IGNORECASE)
        except:
            continue
        for t in titles:
            if pat.search(t):
                hits += 1
                if len(titles_sample) < 3:
                    titles_sample.append(t[:50])
                break
    if hits > 0:
        print("  %s %s: %d hits" % (d["level"], g, hits))
        for s in titles_sample:
            print("    -> %s" % s)
