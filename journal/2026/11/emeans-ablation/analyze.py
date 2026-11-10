import json, glob, statistics as st, collections
rows = []
for f in sorted(["results.jsonl"]):
    for l in open(f):
        try: rows.append(json.loads(l))
        except Exception: pass
groups = collections.defaultdict(list)
ref = {(r["ds"], r["k"], r["seed"]): r["test"] for r in rows if r["arm"] == "lloyd" and r["T"] == 25}
for r in rows:
    key = (r["ds"], r["k"], r["seed"])
    if key in ref: groups[(r["ds"], r["k"], r["arm"], r["T"])].append((r["test"] / ref[key], r["secs"], r.get("B"), r.get("alpha0"), r.get("splits")))
order = ["lloyd", "emeans", "const_alpha", "no_finalize", "no_revival", "macqueen", "macqueen_bare", "sklearn_mbk"]
for ds, k in sorted({(g[0], g[1]) for g in groups}):
    print(f"\n== {ds} n=1M k={k}  (test MSE / Lloyd@25, median over seeds; % above(+)/below(-) Lloyd@25)")
    for arm in order:
        for (d2, k2, a, T), v in sorted(groups.items(), key=lambda x: x[0][3]):
            if (d2, k2, a) != (ds, k, arm): continue
            ratios = [x[0] for x in v]
            print(f"  {arm:14s} T={T:<4} {100*(st.median(ratios)-1):+7.2f}%  range [{100*(min(ratios)-1):+.2f},{100*(max(ratios)-1):+.2f}]  n={len(v)}  secs={st.median([x[1] for x in v]):.1f}  B={v[0][2]} a0={v[0][3]} splits={st.median([x[4] for x in v]) if v[0][4] is not None else '-'}")
