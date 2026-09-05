#!/usr/bin/env python3
"""Generate calibration fixtures for token-adjusted-context from reference tokenizers.

Measures, per (tokenizer, corpus): tokens, chars, chars/token, top bigram tokens,
cross-position seam stats (tokens spanning sample positions), and min/max
per-token char attribution (forward vs backward greedy) for interval bounds.
"""
import json, collections, os, sys
from tokenizers import Tokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
# fixture inputs live next to this script: artifacts/ (tokenizer.json files,
# downloaded from Hugging Face) and corpora/ (see README for exact sources).
ART = os.environ.get("TOK_ART", os.path.join(HERE, "artifacts"))
CORP = os.environ.get("TOK_CORP", os.path.join(HERE, "corpora"))

MODELS = [
    ("Qwen2.5 (7B Instruct)", "Qwen_Qwen2.5-7B-Instruct"),
    ("DeepSeek-V3", "deepseek-ai_DeepSeek-V3"),
    ("GLM-4 (9B chat)", "zai-org_glm-4-9b-chat-hf"),
    ("Mistral v0.1 (7B)", "mistralai_Mistral-7B-v0.1"),
    ("Mistral Small 3.1 (Tekken)", "mistralai_Mistral-Small-3.1-24B-Instruct-2503"),
    ("Gemma 2 (unsloth mirror)", "unsloth_gemma-2-2b-it"),
]

def load_corpus():
    # day-15 pinned fixtures: byte-identical to the corpus used for the
    # 2026-08-31 journal entry, so the reference table is a regression target.
    en = open(f"{CORP}/alice_raw.txt", encoding="utf-8").read()[:120000]
    code = open(f"{CORP}/argparse.py", encoding="utf-8").read()
    zh = open(f"{CORP}/zh_corpus.txt", encoding="utf-8").read()
    ar = open(f"{CORP}/astronomy_ar.txt", encoding="utf-8").read()
    return {"en": en, "code": code, "zh": zh, "ar": ar}

def per_token_char_lens(text, offsets):
    """Chars attributed to each token, greedy forward attribution."""
    n = len(text)
    lens = []
    for i, (a, b) in enumerate(offsets):
        end = offsets[i + 1][0] if i + 1 < len(offsets) else n
        lens.append(max(end - a, b - a))
    return lens

HELDOUT_FRACS = (0.10, 0.25, 0.55, 0.85, 0.97)

def heldout_slices(corpora):
    """Fixed pseudo-random slices per corpus for out-of-sample error checks."""
    out = {}
    for ck, text in corpora.items():
        n = len(text)
        for frac in HELDOUT_FRACS:
            start = int(n * frac) // 2
            length = max(2000, int(n * 0.08))
            out.setdefault(ck, []).append(text[start:start + length])
    return out

def quantiles(sorted_vals):
    def q(p):
        i = min(int(p * len(sorted_vals)), len(sorted_vals) - 1)
        return sorted_vals[i]
    return {"p50": q(0.50), "p95": q(0.95), "max": sorted_vals[-1]}

def nk_enc(tk, text):
    e = tk.encode(text, add_special_tokens=False)
    return e.ids

def top_bigrams(enc, k=30):
    toks = enc.tokens
    cnt = collections.Counter(toks)
    return [[t, c] for t, c in cnt.most_common(k)]

def main():
    corpora = load_corpus()
    for k, v in corpora.items():
        print(f"corpus {k}: {len(v)} chars")
    out = {"generated": "2026-09-05", "tokenizers_version": "0.23.2",
           "models": [], "calibration": {}, "bigrams": {}, "seams": {}, "bounds": {},
           "heldout": {}}
    for label, fname in MODELS:
        tk = Tokenizer.from_file(f"{ART}/{fname}.json")
        tk.no_padding(); tk.no_truncation()
        key = fname
        out["models"].append({"label": label, "key": key})
        vocab = tk.get_vocab_size(with_added_tokens=True)
        slices = heldout_slices(corpora)
        for ck, text in corpora.items():
            enc = tk.encode(text, add_special_tokens=False)
            t = len(enc.ids); c = len(text)
            out["calibration"].setdefault(ck, {})[key] = {
                "tokens": t, "chars": c, "cpt": c / t, "vocab": vocab}
            out["bigrams"].setdefault(ck, {})[key] = top_bigrams(enc)
            # seam probes: 40 evenly spaced positions; does a token span the position?
            offs = enc.offsets
            positions = sorted(set(int(len(text) * (i + 0.5) / 40) for i in range(40)))
            span = 0; checked = 0
            for p in positions:
                hit = next(((a, b) for (a, b) in offs if a < p < b), None)
                # position must fall on a real char boundary for a fair probe
                if p < len(text):
                    checked += 1
                    if hit: span += 1
            out["seams"].setdefault(ck, {})[key] = {"span": span, "checked": checked}
            lens = sorted(per_token_char_lens(text, offs))
            out["bounds"].setdefault(ck, {})[key] = quantiles(lens)
            out["heldout"].setdefault(ck, {})[key] = [
                {"chars": len(s), "tokens": len(nk_enc(tk, s))} for s in slices[ck]]
        print(f"done {label}")
    fx_path = os.path.join(HERE, "fixtures.json")
    with open(fx_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print("wrote", fx_path)
    if len(sys.argv) > 2 and sys.argv[1] == "--embed":
        # splice fresh fixtures + example slices into a built index.html
        page = sys.argv[2]
        html = open(page, encoding="utf-8").read()
        start = html.index("const FIXTURES = ")
        end = html.index("\n", html.index("const EXAMPLES = "))
        examples = {}
        for ck, fname in (("en", "alice_raw.txt"), ("code", "argparse.py"),
                          ("zh", "zh_corpus.txt"), ("ar", "astronomy_ar.txt")):
            text = open(os.path.join(CORP, fname), encoding="utf-8").read()
            if ck == "en":
                text = text[:120000]
            examples[ck] = {"text": text[:5000]}
        payload = ("const FIXTURES = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n"
                   "const EXAMPLES = " + json.dumps(examples, ensure_ascii=False) + ";")
        html = html[:start] + payload + html[end:]
        open(page, "w", encoding="utf-8").write(html)
        print("embedded fixtures into", page, len(html), "bytes")

if __name__ == "__main__":
    main()
