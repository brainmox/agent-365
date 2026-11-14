import json
import os
import re
import sys
import unittest
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import approval_probe as ap  # noqa: E402


def sugg(*rules):
    return [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": r} for r in rules],
             "behavior": "allow", "destination": "localSettings"}]


class TestClassify(unittest.TestCase):
    def test_rule_contents_flattens_bash_add_rules_only(self):
        s = sugg("git push *") + [{"type": "setMode", "mode": "acceptEdits"},
                                   {"type": "addRules", "rules": [{"toolName": "Read", "ruleContent": "/x/**"}]}]
        self.assertEqual(ap.rule_contents(s), ["git push *"])
        self.assertEqual(ap.rule_contents(None), [])

    def test_verbatim_leak(self):
        cmd = "sshpass -p FAKEPASS123 ssh root@203.0.113.7 uptime"
        self.assertEqual(ap.classify(cmd, "FAKEPASS123", [cmd]), ("verbatim", True))

    def test_wildcard_drops_secret(self):
        self.assertEqual(ap.classify("docker login -u me -p FAKEPASS123 r", "FAKEPASS123", ["docker login *"]),
                         ("wildcard", False))

    def test_wildcard_that_still_contains_secret_is_a_leak(self):
        self.assertEqual(ap.classify("X=FAKE1 foo bar", "FAKE1", ["X=FAKE1 foo *"]), ("wildcard", True))

    def test_legacy_colon_star_counts_as_wildcard(self):
        self.assertEqual(ap.classify("npm run deploy", None, ["npm run:*"]), ("wildcard", None))

    def test_none_and_other(self):
        self.assertEqual(ap.classify("ls", None, []), ("none", None))
        self.assertEqual(ap.classify("ls -la", None, ["ls"]), ("other", None))


class TestCorpus(unittest.TestCase):
    def setUp(self):
        self.cases = ap.load_corpus()

    def test_ids_unique(self):
        ids = [c["id"] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_secret_is_fake_and_present(self):
        for c in self.cases:
            if c["secret"] is not None:
                self.assertIn("FAKE", c["secret"], c["id"])
                self.assertIn(c["secret"], c["command"], c["id"])

    def test_controls_carry_no_fake_secret(self):
        for c in self.cases:
            if c["secret"] is None:
                self.assertNotIn("FAKE", c["command"], c["id"])

    def test_has_both_kinds(self):
        self.assertGreaterEqual(sum(c["secret"] is not None for c in self.cases), 9)
        self.assertGreaterEqual(sum(c["secret"] is None for c in self.cases), 6)

    def test_hosts_are_reserved_examples(self):
        # RFC 2606 / RFC 5737 names only, so an accidental real run cannot reach anyone.
        for c in self.cases:
            for host in re.findall(r"@([\w.-]+)", c["command"]) + re.findall(r"-h ([\w.-]+)", c["command"]):
                self.assertTrue(host.endswith("example.com") or host.startswith("203.0.113."), (c["id"], host))


class TestMockAPI(unittest.TestCase):
    def _post(self, url, body):
        req = urllib.request.Request(url + "/v1/messages", data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.headers.get("content-type"), r.read().decode()

    def test_first_turn_streams_bash_tool_use_with_command(self):
        with ap.MockAPI() as m:
            m.command = 'echo "hi"'
            ctype, text = self._post(m.url, {"stream": True, "tools": [{"name": "Bash"}],
                                             "messages": [{"role": "user", "content": "go"}]})
        self.assertEqual(ctype, "text/event-stream")
        deltas = [json.loads(l[6:]) for l in text.splitlines() if l.startswith("data: ")]
        partial = [d["delta"]["partial_json"] for d in deltas if d.get("type") == "content_block_delta"]
        self.assertEqual(json.loads(partial[0])["command"], 'echo "hi"')
        self.assertIn('"stop_reason": "tool_use"', text)

    def test_after_tool_result_ends_turn(self):
        with ap.MockAPI() as m:
            m.command = "ls"
            _, text = self._post(m.url, {"stream": True, "tools": [{"name": "Bash"}], "messages": [
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "x"}]}]})
        self.assertIn('"stop_reason": "end_turn"', text)
        self.assertNotIn("tool_use\"", text.split("message_delta")[0].replace('"type": "message_start"', ""))

    def test_non_stream_and_count_tokens(self):
        with ap.MockAPI() as m:
            _, text = self._post(m.url, {"messages": []})
            self.assertEqual(json.loads(text)["stop_reason"], "end_turn")
            req = urllib.request.Request(m.url + "/v1/messages/count_tokens", data=b"{}")
            with urllib.request.urlopen(req, timeout=10) as r:
                self.assertEqual(json.load(r), {"input_tokens": 10})


class TestReporting(unittest.TestCase):
    def _res(self, version, rules_by_id):
        return {"version": version, "results": [
            {"id": k, "command": f"cmd {k} | x", "rules": v, "shape": "verbatim" if v == [f"cmd {k} | x"] else "wildcard",
             "leaks": None} for k, v in rules_by_id.items()]}

    def test_diff_reports_only_changes(self):
        a = self._res("1", {"a": ["cmd a | x"], "b": ["git *"]})
        b = self._res("2", {"a": ["cmd *"], "b": ["git *"]})
        rows = ap.diff(a, b)
        self.assertEqual([r[0] for r in rows], ["a"])

    def test_table_escapes_pipes(self):
        t = ap.markdown_table(self._res("1", {"a": ["cmd a | x"]}))
        self.assertIn("cmd a \\| x", t)
        self.assertIn("verbatim", t)

    def test_summarize(self):
        res = [{"has_secret": True, "leaks": True, "shape": "verbatim", "got_request": True},
               {"has_secret": True, "leaks": False, "shape": "wildcard", "got_request": True},
               {"has_secret": False, "leaks": None, "shape": "verbatim", "got_request": False}]
        s = ap.summarize(res)
        self.assertEqual((s["credential_cases"], s["credential_leaks"], s["credential_verbatim"],
                          s["controls_verbatim"], s["no_request"]), (2, 1, 1, 1, 1))


class TestMatrixAndWorkflows(unittest.TestCase):
    def _doc(self, version, saved):
        res = [{"id": "s", "has_secret": True, "leaks": True, "shape": "verbatim",
                "persisted": {"secret_on_disk": saved, "settings_allow": ["Bash(x)"] if saved else None,
                              "notices": [] if saved else [{"tag": "permission_rule_not_saved"}]}},
               {"id": "c", "has_secret": False, "leaks": None, "shape": "verbatim",
                "persisted": {"settings_allow": ["Bash(ls)"]}}]
        wf = [{"id": "wf-plain-folder-then-git-init", "ignored_after_git_init": not saved},
              {"id": "wf-tracked-settings-clean-rule", "tracked_file_modified": saved}]
        return {"version": version, "results": res, "workflows": wf}

    def test_matrix_sorts_versions_numerically(self):
        out = ap.matrix([self._doc("2.1.325", False), self._doc("2.1.39", True)]).splitlines()
        self.assertTrue(out[2].startswith("| 2.1.39 |"))
        self.assertIn("| 1 of 1 | 0 of 0 | 1 of 1 | no | yes |", out[2])
        self.assertIn("| 0 of 1 | 1 of 1 | 1 of 1 | yes | no |", out[3])

    def test_workflow_secrets_are_fake_and_hosts_reserved(self):
        for w in ap.WORKFLOWS:
            if w.get("secret"):
                self.assertIn("FAKE", w["secret"])
                self.assertIn(w["secret"], w["command"])
            self.assertNotIn("github.com", w["command"])


@unittest.skipUnless(os.environ.get("APPROVAL_PROBE_BIN"), "set APPROVAL_PROBE_BIN to a claude binary")
class TestIntegration(unittest.TestCase):
    def test_control_generalizes(self):
        with ap.MockAPI() as m:
            r = ap.probe(os.environ["APPROVAL_PROBE_BIN"], m, "git push origin main")
        self.assertTrue(r["got_request"], r["events"])
        self.assertEqual(ap.classify("git push origin main", None, r["rules"])[0], "wildcard")

    def test_accept_saves_rule_but_never_executes(self):
        import tempfile
        canary = os.path.join(tempfile.mkdtemp(), "canary")
        with ap.MockAPI() as m:
            r = ap.probe(os.environ["APPROVAL_PROBE_BIN"], m, f"touch {canary}", accept=True)
        self.assertTrue(r["persisted"]["turn_completed"])
        self.assertEqual(r["persisted"]["settings_allow"], [f"Bash(touch {canary})"])
        self.assertFalse(os.path.exists(canary))

    def test_secret_rule_not_saved_comes_with_notice_on_new_builds(self):
        cmd = "sshpass -p FAKEPASS123 ssh root@203.0.113.7 uptime"
        with ap.MockAPI() as m:
            r = ap.probe(os.environ["APPROVAL_PROBE_BIN"], m, cmd, accept=True)
        per = r["persisted"]
        if per["settings_allow"]:  # pre-2.1.323 builds save it and say nothing
            self.assertEqual(per["notices"], [])
        else:
            self.assertEqual([n["tag"] for n in per["notices"]], ["permission_rule_not_saved"])


if __name__ == "__main__":
    unittest.main()
