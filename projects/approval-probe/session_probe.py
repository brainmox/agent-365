"""Multi-turn checks for approval-probe.

1. Does a rule that was approved but not saved really last "for this session only"?
   One Claude Code process, two user turns; the mock asks for a command in each turn.
   Turn 1 is approved with the suggested rules (command swapped for `true`, as in the
   main probe). Turn 2 is NOT swapped: if Claude Code does not ask, the command runs,
   so session cases only use commands whose binaries are absent (psql, sshpass), which
   fail locally with "command not found". The turn-2 tool result proves what ran.
2. After the run, which files on disk contain the fake secret? (settings file, session
   transcript under ~/.claude/projects/), and with the two documented opt-outs.
"""
import json
import os
import re
import select
import shutil
import subprocess
import tempfile
import time

import approval_probe as ap


class TurnMock(ap.MockAPI):
    """A Bash tool_use whenever the newest content block is user text; a text answer
    right after a tool_result. Claude Code merges the next user turn into the message
    that carries the previous tool_result, so the decision uses the LAST block."""

    def __init__(self):
        super().__init__()
        self.plan, self.results, self._seen, self._n = [], [], set(), 0

    @staticmethod
    def newest_is_tool_result(messages):
        last = messages[-1] if messages else {}
        c = last.get("content")
        blocks = [x for x in c if isinstance(x, dict)] if isinstance(c, list) else [{"type": "text"}]
        return bool(blocks) and blocks[-1].get("type") == "tool_result"

    def reply(self, body):
        msgs = body.get("messages", [])
        for m in msgs:
            for x in (m.get("content") if isinstance(m.get("content"), list) else []):
                if isinstance(x, dict) and x.get("type") == "tool_result" and x.get("tool_use_id") not in self._seen:
                    self._seen.add(x.get("tool_use_id"))
                    self.results.append(json.dumps(x.get("content"))[:200])
        tools = [t.get("name") for t in body.get("tools", []) if isinstance(t, dict)]
        if body.get("stream") and "Bash" in tools and self.plan and not self.newest_is_tool_result(msgs):
            self.command = self.plan.pop(0)
            self._n += 1
            out = super().reply({**body, "messages": []})
            return out.replace(b"toolu_mock1", f"toolu_turn{self._n}".encode())
        return super().reply({**body, "messages": [{"content": [{"type": "tool_result"}]}]})


def session(exe, commands, root=None, extra_args=(), extra_env=None, timeout=45):
    """One process, one user turn per command. Returns per-turn prompted/notices, the
    tool results Claude Code sent back, the saved allow list, and the run's root dir
    (caller removes it)."""
    root = root or tempfile.mkdtemp(prefix="approval-session-")
    home, proj = os.path.join(root, "home"), os.path.join(root, "proj")
    os.makedirs(home, exist_ok=True)
    if not os.path.exists(proj):
        os.makedirs(proj)
        subprocess.run(["git", "init", "-q", proj], check=True)
    with TurnMock() as m:
        m.plan = list(commands)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_"))}
        env.update(HOME=home, ANTHROPIC_BASE_URL=m.url, ANTHROPIC_API_KEY="mock-not-a-key",
                   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1", DISABLE_AUTOUPDATER="1", **(extra_env or {}))
        p = subprocess.Popen([exe, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
                              "--verbose", "--permission-prompt-tool", "stdio", *extra_args],
                             cwd=proj, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
        turns = []
        try:
            for i, _ in enumerate(commands):
                p.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": f"turn {i + 1}"}}) + "\n")
                p.stdin.flush()
                prompted, notices, done, end = False, [], False, time.time() + timeout
                while time.time() < end:
                    ready, _, _ = select.select([p.stdout], [], [], 1)
                    if not ready:
                        if p.poll() is not None:
                            break
                        continue
                    line = p.stdout.readline()
                    if not line:
                        break
                    try:
                        j = json.loads(line)
                    except ValueError:
                        continue
                    if j.get("type") == "control_request" and (j.get("request") or {}).get("subtype") == "can_use_tool":
                        prompted = True
                        req = j["request"]
                        resp = {"type": "control_response", "response": {
                            "subtype": "success", "request_id": j["request_id"],
                            "response": {"behavior": "allow",
                                         "updatedInput": {**req.get("input", {}), "command": "true"},
                                         "updatedPermissions": req.get("permission_suggestions") or []}}}
                        p.stdin.write(json.dumps(resp) + "\n")
                        p.stdin.flush()
                    if j.get("type") == "system" and "permission_rule" in str(j.get("tag", "")):
                        notices.append(j.get("tag"))
                    if j.get("type") == "result":
                        done = True
                        break
                turns.append({"turn": i + 1, "prompted": prompted, "notices": notices, "completed": done})
            time.sleep(0.5)
        finally:
            p.kill()
            p.wait(timeout=10)
            p.stdin.close()
            p.stdout.close()
    s = os.path.join(proj, ".claude", "settings.local.json")
    allow = None
    if os.path.exists(s):
        with open(s) as f:
            allow = (json.load(f).get("permissions") or {}).get("allow")
    return {"turns": turns, "tool_results": list(m.results), "saved": allow, "root": root}


def files_containing(root, needle):
    """Relative paths under root whose text contains needle, with occurrence counts.
    Session ids and temp project names are normalized."""
    out = {}
    for dirpath, _, names in os.walk(root):
        for n in names:
            path = os.path.join(dirpath, n)
            try:
                with open(path, errors="ignore") as f:
                    k = f.read().count(needle)
            except OSError:
                continue
            if k:
                rel = os.path.relpath(path, root)
                rel = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<session>", rel)
                rel = re.sub(r"projects/-[^/]*", "projects/<project>", rel)
                out[rel] = k
    return out


PG = 'PGPASSWORD=FAKEPASS123 psql -h db.example.com -U app -c "select 1"'
PG_OTHER = 'PGPASSWORD=FAKEPASS456 psql -h db.example.com -U app -c "select 1"'
SSH = "sshpass -p FAKEPASS123 ssh root@203.0.113.7 uptime"
CLEAN = 'psql -h db.example.com -U app -c "select 1"'
POSITIONAL = "./deploy.sh FAKETOKEN123"

SESSION_CASES = [
    {"id": "secret-env-same-twice", "commands": [PG, PG], "restart": True},
    {"id": "secret-sshpass-same-twice", "commands": [SSH, SSH], "restart": False},
    {"id": "clean-same-twice", "commands": [CLEAN, CLEAN], "restart": True},
    {"id": "secret-then-different-secret", "commands": [PG, PG_OTHER], "restart": False},
]

DISK_CASES = [
    {"id": "env-prefix", "command": PG, "secret": "FAKEPASS123", "args": [], "env": {}},
    {"id": "positional", "command": POSITIONAL, "secret": "FAKETOKEN123", "args": [], "env": {}},
    {"id": "env-prefix+CLAUDE_CODE_SKIP_PROMPT_HISTORY", "command": PG, "secret": "FAKEPASS123", "args": [],
     "env": {"CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1"}},
    {"id": "env-prefix+--no-session-persistence", "command": PG, "secret": "FAKEPASS123",
     "args": ["--no-session-persistence"], "env": {}},
]


def run_session_checks(exe):
    sessions, disk = [], []
    for c in SESSION_CASES:
        r = session(exe, c["commands"])
        row = {"id": c["id"], "turns": r["turns"], "tool_results": r["tool_results"], "saved": r["saved"]}
        if c["restart"]:
            r2 = session(exe, c["commands"][:1], root=r["root"])
            row["after_restart_prompted"] = r2["turns"][0]["prompted"]
        shutil.rmtree(r["root"], ignore_errors=True)
        sessions.append(row)
    # A secret rule saved by an older version: kept when the file is rewritten? still honored?
    root = tempfile.mkdtemp(prefix="approval-session-")
    proj = os.path.join(root, "proj")
    os.makedirs(os.path.join(proj, ".claude"))
    subprocess.run(["git", "init", "-q", proj], check=True)
    legacy = PG.replace("FAKEPASS123", "FAKEPASS999")
    with open(os.path.join(proj, ".claude", "settings.local.json"), "w") as f:
        json.dump({"permissions": {"allow": [f"Bash({legacy})"]}}, f)
    r = session(exe, [CLEAN, legacy], root=root)
    sessions.append({"id": "legacy-secret-rule-then-clean-save", "turns": r["turns"],
                     "tool_results": r["tool_results"], "saved": r["saved"],
                     "legacy_rule_kept": f"Bash({legacy})" in (r["saved"] or [])})
    shutil.rmtree(root, ignore_errors=True)
    for c in DISK_CASES:
        r = session(exe, [c["command"]], extra_args=c["args"], extra_env=c["env"])
        disk.append({"id": c["id"], "saved": bool(r["saved"]), "files": files_containing(r["root"], c["secret"])})
        shutil.rmtree(r["root"], ignore_errors=True)
    return {"sessions": sessions, "disk": disk}
