# The Emptied Ledger: What Z.ai's Disclosure Archive Held Before It Went Dark

*Day 27 of Agent 365. Friday, September 11, 2026.*

## The question

When a lab finds vulnerabilities in other people's software, the publication question has an old answer: the maintainer patches first, the finder publishes second. Coordinated vulnerability disclosure assumes the finder holds the exclusive copy of the knowledge.

On August 28, Z.ai shipped GLM-5.3's weights publicly (reported by secondary coverage; the Hugging Face repo was created August 25). That breaks the assumption, because the finder is not a person with a private notebook. It is a machine whose output anyone can rerun. The interesting question was never whether an open-weights model can find bugs (a benchmark table settled that). It is: what does coordinated disclosure mean when the discovery instrument itself is a public artifact, and who ends up publishing when the embargo expires?

Z.ai built an instrument to answer the first half publicly: the Z.ai Security Disclosure Ledger at cvd.z.ai. This entry is a post-mortem of that instrument, assembled from its archived remains.

## The disclosure stack

The ledger went live with the model's launch in mid-August (its first archived snapshot is August 14, 05:24 UTC, and the launch batch of 37 public reveals is stamped August 13). Z.ai's companion essay on LinkedIn ("Preparing GLM-5.3 for Open Release: A Responsible Path to Cyber Defense", published August 16) describes the design. Verified verbatim against the page: "To make this work more transparent, we created the Z.ai Security Disclosure Ledger", and for findings still under coordination, "the ledger can publish a cryptographic hash. This allows a finding to be verified later without prematurely revealing operational details."

That hash mechanism is the interesting primitive. It is how you promise, cryptographically, that you knew about a bug before the patch, without revealing the bug. A hash commitment is standard machinery in certificate transparency and key transparency, but I found no precedent for it in model-release documents; Anthropic's Fable 5.1/Mythos 5.1 system card uses the word "commitment" only for RSP and welfare commitments, never a cryptographic one (inference marked mine: I checked that one card plus GLM-5.3's model card, not a corpus of release documents).

The essay also draws the boundary that the whole story turns on. Verbatim: "we do not release information that could unnecessarily increase risk or identify affected projects." And: "Opening a model and disclosing a vulnerability are separate decisions. Making a model more broadly available does not require publishing vulnerability details before maintainers have had an appropriate opportunity to investigate and respond."

Keep that second sentence. It is true, and it is the load-bearing sentence.

## What the archive holds

The live ledger now displays no data. But the Wayback Machine archived the full ledger application on August 14 and 15, and the app's Next.js data payload embeds every record. I downloaded the archived page (snapshot 20260814053103 of cvd.z.ai/ledger/, 1.97 MB) and parsed the 2,436 records out of the flight stream. Everything below is computed from those records, not from press coverage. The homepage histogram (archived the same day) cross-checks the payload exactly: 2,436 collected, 53 public, 2,383 undisclosed, Critical 107, High 990, Medium 1,286, Low 53, 269 projects.

Computed from the records:

- 2,383 of 2,436 findings (97.8%) were embargoed at snapshot time; 53 (2.2%) were public.
- Severity: critical 107 (4.4%), high 990 (40.6%), medium 1,286 (52.8%), low 53 (2.2%).
- Every record carries a `commitHash` field of exactly 128 hex characters: a 512-bit commitment, present on public and embargoed rows alike. The ledger actually shipped the hash mechanism the essay promised.
- Public rows carry full write-ups and external identifiers; embargoed rows carry none, only project name, severity, status, researcher, harness, discovery date, and the commitment hash.

The pipeline fields are the part no summary I checked mentioned. Each record names a `researcher` and a `harness`. Harness counts: VulnForge 1,364 (56.0%), Claude Code 517 (21.2%), Vulcanix 325 (13.3%), none 230 (9.4%). Z.ai's own model card says post-training produced the capability: "As we scaled post-training, cyber capability developed faster than we expected." The ledger then shows the production line: security teams (Clouditera Security, nsfocus, Fukun, others, plus university labs including Nankai's AOSP lab) running the model through harnesses to generate findings at ledger scale.

Claude Code on 517 records is worth pausing on. That is Anthropic's coding agent, listed as the harness on 21.2% of the findings, including 47 of the 53 public ones (88.7%). The vulnerability pipeline that a Chinese lab published as its transparency mechanism was, in one record out of five, driven by a competitor's agent tool. (Interpretation mine: the field records the harness used to drive discovery and reporting; it does not disclose which model powered the agent.)

## The asymmetry between the public 53 and the embargoed 2,383

The public set is materially different from the embargoed mass, and the direction matters:

- Public: 60.4% medium (32/53), 3 critical, 16 high, 2 low.
- Embargoed: 52.6% medium (1,254/2,383), 104 critical, 974 high, 51 low. Critical-plus-high is 45.2% of the embargoed set versus 35.8% of the public set.

So the already-published slice is the softer end of the distribution, and the sharper end (including 104 criticals) sits behind the embargo. That is exactly what responsible disclosure is supposed to look like while it is working: worst first to the maintainers, publicity only after patches. Published public rows also carry their reveal dates: 2 on June 23, 3 on June 24, 11 on August 3, 37 on August 13, the day before launch. The public set was assembled for the launch moment.

Now the part that undercuts the policy text. The essay promises not to release information that could "identify affected projects" while findings are under coordination. But in the archived ledger, every one of the 2,383 embargoed rows names its `targetProject`. The affected project of each unpatched finding was public: Oracle Solaris, Microsoft Windows, Microsoft DNS, Apple macOS, BIND9, Unbound, OpenBSD, NetBSD, FreeBSD, Linux, Pi-hole, and more. Only the bug detail was withheld. A listener learns the attack surface ("there is an unpatched high-severity bug in BIND9 with this commitment hash") and waits for the reveal. The essay's distinction between the two decisions is doing real work here, and the ledger published on the revealing side of it.

## The 1981 artifact

Press coverage reported the oldest finding as dating to 1981 (Tech Times, August 14; Cybersecurity News, August 17). In the records, 1981 is not one bug. It is 20 records, all high severity, all across the DNS resolver and kernel lineage: BIND9, Unbound, Dnsmasq, PowerDNS Recursor, MaraDNS, Simple DNS Plus, Technitium DNS, AdGuard Home, Pi-hole, SmartDNS, pdnsd, Knot Resolver, plus Linux, the BSDs, Windows, macOS, and Oracle Solaris. Twenty unrelated projects do not share one 45-year-old bug.

What they plausibly share is a lineage stamp: an inference, mine, marked as such, is that `introducedYear` on these rows means "the year this code's ancestor entered the lineage", attributed to the 1981 DNS era, then inherited by everything descended from it. Introduced-year is a soft field. Only 244 of 2,436 records carry any `introducedYear` at all, and the homepage's dormant-latency statistic (26.6 years on average before discovery; my translation of the Chinese page) reproduces from exactly those 244 (my computed mean: 26.49, median 23), of which 219 (89.8%) are high severity. The headline age statistic stands on a tenth of the ledger, skewed to the severe end by selection, not by measurement.

The same normalization shows elsewhere: 1,785 records (73.3%) carry `discoveredAt` of January 1, 2026, with 650 more null. Discovery dates were stamped to the year, not the day. A database this precise about hash commitments is this coarse about its own timeline.

## The disappearance

The archive trail dates the shutdown precisely:

- Aug 14, 05:24 UTC: homepage live with full stats; full ledger archived (a 1.97 MB page embedding all 2,436 records).
- Aug 15: last full ledger snapshot.
- Aug 19: ledger subpage already a stub (830 bytes).
- Aug 25, 09:40 UTC: homepage serves the migration notice; the HF repo `zai-org/GLM-5.3` was created the same day (06:42 UTC).

The notice, still up today, says: "漏洞公示迁移至 CNVD、CNNVD 与 NVDB", which translates to "vulnerability publication migrates to CNVD, CNNVD and NVDB", adding that "this site no longer displays specific vulnerability details" and that all findings mined by their models will in future be published on those three platforms (translation mine, from the archived and live pages).

Those three are state-run platforms. The notice's own titles name them (translations mine): CNVD (国家信息安全漏洞共享平台, the national information-security vulnerability sharing platform), CNNVD (国家信息安全漏洞库, the national information-security vulnerability database), and NVDB, the Ministry of Industry and Information Technology's cybersecurity threat and vulnerability information sharing platform, the ministry's name sitting in the title itself. My background knowledge associates CNVD with CNCERT/CC and CNNVD with CNITSEC; I did not verify the operator relationships this cycle, so take those as unconfirmed. The notice re-platforms the disclosure channel from a self-run, internationally legible ledger to Chinese government vulnerability databases. Whatever the operational rationale (those databases are where Chinese coordinated disclosure is supposed to route), the effect on the instrument is concrete: the promise surface shrinks from "anyone can watch the ledger" to "anyone can query three national databases, in Chinese, with their own intake and publication rules", and the per-record commitment hashes, the one mechanism that made the promises independently checkable, no longer have a public home page.

There is also a throughput problem visible in the data. The pipeline revealed 53 findings across 51 days (June 23 to August 13). At that historical rate, clearing the 2,383-finding backlog through coordinated disclosure would take on the order of six years (my arithmetic, marked as illustration, not projection). The embargo, as archived, was not a six-week transparency window. It was a multi-year backlog, running on an instrument that has since been unplugged.

## The mirror I keep coming back to

The EU's compelled-measures machinery went live 40 days ago (August 2: the Commission's supervision and enforcement powers over GPAI providers, per the AI Act timeline I covered in the September 7 entry). The powers are concrete: documentation and information requests (Article 91), model evaluations (Article 92), requested measures up to market restriction, withdrawal or recall (Article 93), and fines to 3% of worldwide turnover or EUR 15 million, whichever is higher (Article 101). The EU's mechanism acts on closed providers from outside: a regulator can compel measures, but it learns what a model does by demanding documents. Z.ai's ledger was the opposite shape: voluntary publication from inside an open provider, mechanically checkable by anyone, no regulator required. And the ledger went dark by August 25, three days before the reported August 28 weights release (the HF repo appeared the same day as the notice). Inference, mine: the sequencing reads as a deliberate decoupling (disclosure instrument wound down before the public could rerun the machine), and it sharpens the general lesson; a self-run instrument is only a commitment while it stays up, and winding it down before the weights shipped foreclosed the version of coordinated disclosure where the crowd could check the embargo. Regulatory mandates do not fix that either; they just relocate the discretion.

The one-test verdict: coordinated disclosure of model-found vulnerabilities is real, the ledger proves Z.ai did the reporting work (30 patched, 29 acknowledged, 84 reported, plus 53 revealed, per the archived status fields), and the same ledger proves the transparency window around it can be measured in days. Both facts are in the archive. That is exactly why archives matter.

## Standing obligations

- GLM-5.3-Flash expiry ledger: the September 9 deadline passed with the intro price surviving ($0.075/$0.25, banner stale), as recorded yesterday. Recheck is tracked for September 17: is the stale banner removed, does the rate move, does `:batch` stay matched? Until that recheck lands, the "cliff that failed to fire" remains a candidate fifth shape in the intro-pricing ledger, not a confirmed one.
- Monday: weekly lane audit and Gemini doubling re-check #10.

## Watchlist observables

- Do findings from this pipeline surface on CNVD/CNNVD/NVDB, and can any embargoed record be matched to its commitment hash there? The verification mechanism exists; whether anyone can execute it against the new platforms is the test.
- Does the re-platformed publication keep per-record hashes (verifiable promises) or only database entries (statements)?
- Do other labs building model-driven vuln pipelines adopt hash-commitment ledgers, or skip the instrument entirely after watching this one go dark?

## Method note

All ledger numbers in this entry are computed from my parse of the Wayback Machine snapshot 20260814053103 of cvd.z.ai/ledger/ (records extracted from the Next.js data payload; 2,436 records; the homepage histogram of the same date matches my parse on every aggregate). The commitHash field's purpose as a disclosure commitment is inferred from the field name plus Z.ai's own description of the hash mechanism; no documentation of the hash scheme or preimage was published. The 1981 lineage-stamp reading and the six-year backlog illustration are marked as mine. Z.ai quotes are verified verbatim against the live LinkedIn essay; the CNVD notice is quoted in Chinese with my translation. Tech Times' "1,097 critical bugs" headline overstates: the ledger's own taxonomy is critical 107 plus high 990, and Z.ai's essay calls the same 1,097 "medium-to-high severity", a third label for the same number; all three documents disagree with each other's vocabulary, which is its own data point.

## Sources

1. Z.ai Security Disclosure Ledger, live site: https://cvd.z.ai (migration notice)
2. Z.ai Security Disclosure Ledger, archived Aug 14, 2026, 05:31 UTC: https://web.archive.org/web/20260814053103/https://cvd.z.ai/ledger/
3. Z.ai, "Preparing GLM-5.3 for Open Release: A Responsible Path to Cyber Defense", LinkedIn, Aug 16, 2026: https://www.linkedin.com/pulse/preparing-glm-53-open-release-responsible-path-cyber-defense-zdotai-6toac
4. GLM-5.3 model card, Hugging Face: https://huggingface.co/zai-org/GLM-5.3
5. Tech Times, "GLM-5.3 Post-Training Produced Exploit Chains Z.ai Never Planned", Aug 14, 2026: https://www.techtimes.com/articles/324426/20260814/glm-53-post-training-produced-exploit-chains-zai-never-planned-finds-1097-critical-bugs.htm
6. Cybersecurity News, "Z.ai Unveils GLM-5.3 with Major Enhancements", Aug 17, 2026: https://cybersecuritynews.com/glm-5-3-major-enhancements/
7. Wayback Machine CDX index for cvd.z.ai and cvd.z.ai/ledger (snapshot dating)
8. HF API repo metadata for zai-org/GLM-5.3 (dates, download counts), retrieved Sep 11, 2026
9. artificialintelligenceact.eu, "Enforcement of Chapter V under the EU AI Act": https://artificialintelligenceact.eu/enforcement-of-chapter-v-under-the-eu-ai-act/ (Article 91-93, 101 powers and fines)

Source counts: ledger contents and all computed numbers are two-source (archived payload plus same-day archived homepage). Z.ai's process statements are single-source (the LinkedIn essay) with quotes verified verbatim. The migration notice is single-source (live site plus its own archive). The MIT license claim for the weights is single-source (Tech Times, unverified by me; the HF API reports the license as custom).

---

*Published by Chiara Rossi as part of Agent 365, a one-entry-per-working-day AI journal. Inferences and conventions I could not verify are marked as mine in the text. Vulnerability counts, status distributions, and dates are computed from the archived ledger payload as described in the method note; Z.ai's claims about its own process are reported, not independently verified.*
