#!/usr/bin/env python3
"""Smart daily briefing: identity changes by day of week"""
import json, os, sys, urllib.request
from datetime import datetime
sys.path.insert(0, "/root/projects/invest/scripts")
sys.path.insert(0, "/root/projects/search_information/search_information/scripts")

WH = os.environ.get("DINGTALK_WEBHOOK", "")
SCHEDULE = {0:"INVESTOR",1:"INVESTOR",2:"INVESTOR",3:"INVESTOR",4:"INVESTOR",5:"STUDENT",6:"CONSUMER"}
DAY_NAMES = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"}
TITLE_MAP = {"INVESTOR":"Invest","STUDENT":"Career","DEV":"Tech","CONSUMER":"Deals"}
EMOJI_MAP = {"INVESTOR":"📈","STUDENT":"🎓","DEV":"💻","CONSUMER":"🛍️"}

def load_cfg():
    p = "/root/projects/search_information/search_information/TrendRadar/config/identity_config.json"
    if os.path.exists(p):
        with open(p) as f: return json.load(f)
    return {"groups": {}, "daily_limit": 3}

def load_clf():
    try:
        from classifier_server import ONNXClassifier
        return ONNXClassifier()
    except: return None

def onnx_filter(texts, clf, th=0.6):
    if not clf or not texts: return texts
    results = clf.predict(texts)
    f = []
    for t, r in zip(texts, results):
        if r.get("label","neutral") != "neutral" and r.get("score",0) >= th:
            f.append(t)
    return f if f else texts[:2]

def get_id(content, groups):
    for g, i in groups.items():
        if g.lower() in content.lower(): return i
    return None

def main():
    now = datetime.now()
    dow = now.weekday()
    tid = SCHEDULE.get(dow, "INVESTOR")
    print("[Briefing]", now.strftime("%m-%d"), DAY_NAMES.get(dow,"?"), "->", tid)

    clf = load_clf()
    cfg = load_cfg()
    groups = cfg.get("groups", {})
    limit = cfg.get("daily_limit", 3)

    sf = "/root/projects/data/invest/knowledge/signals.json"
    if not os.path.exists(sf): print("No signals"); return
    with open(sf) as f: signals = json.load(f).get("signals", [])

    signals.sort(key=lambda s: (
        {"🔴":0,"🟡":1,"⚪":2}.get(s.get("level","⚪"),99), s.get("timestamp","")))

    matched = [s for s in signals if get_id(s.get("content",""), groups) in [tid, None]]

    seen = set()
    cand = []
    for s in matched:
        c = s.get("content","")
        if c and c not in seen: seen.add(c); cand.append((c, s.get("level","⚪")))

    texts = [x[0] for x in cand[:10]]
    filtered = onnx_filter(texts, clf)

    lines = [EMOJI_MAP.get(tid,"📡") + " " + now.strftime("%m-%d") + " " + TITLE_MAP.get(tid,"") + "\n"]

    if tid == "INVESTOR":
        hp = "/root/projects/data/invest/sentiment/sentiment_history.json"
        if os.path.exists(hp):
            with open(hp) as f: d = json.load(f)
            if d: lines.append("**Sentiment: " + str(int(d[-1].get("index",50))) + " (" + d[-1].get("level","") + ")**\n")
        # 预测
        try:
            sys.path.insert(0, "/root/projects/search_information/search_information/scripts")
            from predictor import brief_prediction
            pred = brief_prediction()
            if pred and not "数据不足" in pred:
                lines.append("🔮 " + pred + "\n")
        except: pass

    shown = 0
    for c, lvl in cand:
        if c in filtered:
            lines.append("- " + lvl + " " + c[:60] + "\n")
            shown += 1
            if shown >= limit: break
    if shown == 0 and cand:
        lines.append("- " + cand[0][1] + " " + cand[0][0][:60] + "\n")

    content = "".join(lines)
    print(content)

    if WH:
        payload = {"msgtype":"markdown","markdown":{"title":now.strftime("%m-%d")+" "+TITLE_MAP.get(tid,""),"text":content}}
        req = urllib.request.Request(WH, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            r = json.loads(resp.read())
            print("Sent" if r.get("errcode")==0 else "Fail"+str(r))
        except Exception as e: print("Error:", e)

if __name__ == "__main__": main()
