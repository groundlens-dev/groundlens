# GroundLens FAQ

Short answers to the questions people ask before they run
`pip install groundlens`. The [README](README.md) covers how to use it.

## 1. What is "AI verification infrastructure"?

The layer of your stack that checks what an AI system said against what it
was allowed to say, and keeps proof of the check.

Every serious deployment already has infrastructure for observing models
(traces, latency, token counts) and for evaluating them before release
(benchmarks, eval suites). Verification is a third thing: at the moment an
answer is produced, run independent checks on its content, decide what to do
with it under rules your organisation wrote, and keep a record that a third
party can verify later without trusting you. GroundLens is that layer: a set
of verifiers, a policy engine that interprets their evidence, and a signed,
hash-chained evidence record.

## 2. Why do I need a different infrastructure?

Think of an agentic deployment in a bank answering questions about loan agreements. You have wired in a numeric regex, an NLI model, maybe an LLM judge, and thresholds in a config file. It works. Six months later a customer disputes an answer, or an auditor samples a hundred conversations under the AI Act's record-keeping duty. You have to consider the following:

- First, the checks lived inside your process, so the only evidence they ran is your own log. The auditor has to trust your application to trust the check. That is not verification; it is your word.

- Second, the checks lived inside your dependency tree, so nobody can reproduce them. The NLI model was whatever the Hub served that day, the judge was a hosted model that has since been updated, the threshold was changed in a commit nobody remembers. The score you logged cannot be recomputed, so it cannot be contested and cannot be defended.

- Third, the rules lived in code, so "why did this fail" is a reading of your codebase at that commit, not a document a risk officer can sign.

Infrastructure means moving those three things out of the application and into a layer that is independent of it, the way an auditor is independent of the company it audits. That is what the engine is: one implementation of the pipeline (claims → verifiers → evidence → policy → decision → record) that gives the same record for the same input, policy and models, whether it runs inside your agent, from the command line in CI, or on the auditor's laptop. The verifiers are pinned by hash and declare what they guarantee. The rules are a versioned, hashed policy file, not code. The output is a signed, chained record that anyone can verify offline without asking you.


## 3. How do I integrate it?

Call it where the answer is produced, before the answer is used. In Python:

```python
from groundlens import verify

record = verify(answer, sources, question=question, policy="eu_ai_act_high_risk_v1")
if record.decision == "FAIL":
    ...  # block, rewrite, or route to a human; the record says why
record.append_to("records.jsonl")
```

`sources` are the passages your retriever (RAG system) handed the model, with ids so the
record can point at them. The same call exists as a command line
(`groundlens verify`). Whoever checks the records needs no Python: a single
`glv` binary verifies them offline. There is no server to run and nothing to configure for the
first call; the engine has no dependencies and opens no network connection.

If you keep a log, each record links to the previous one; `groundlens
record verify` checks the whole chain and `groundlens report` turns it into
the files an auditor reads.

## 4. Does GroundLens include its own metrics?

Yes, and they are the ones that ship first because they are the ones we
can guarantee.

`groundlens.numeric` reads numbers, currencies, percentages and physical
units in several locales and compares them exactly in base units: `1.2 km`
equals `1200 m`, `212 °F` equals `100 °C`, `$37.35 billion` equals a table
cell `37,350` under "in millions of dollars". It is bit-identical on every
machine because no floating point is involved.

`groundlens.rules` runs your own symbolic rules (an APR must be a
percentage, a date must fall inside the contract term) as a verifier with
the same guarantees.

`groundlens.scope` fails a real figure taken from the wrong company, contract
or version, and `groundlens.intent` sends to review a figure that is not the
kind or unit the question asked for. All of them are exact and need no model.

## 5. Which other metrics can I use?

In the default path, with no model: numeric (with exact arithmetic for
figures the answer computed), scope, intent and units, and your rules. On top,
the judge: the model you already use, asked a fixed question per sentence,
which can only send an answer to review. Every one of them fits the same
contract: input in, evidence out, never a verdict.

Versions before 6.0 also had lexical, entailment (NLI) and similarity channels
on a downloaded model. They were removed: on real answers they checked that
words were present, not that a figure was bound to the right company, year or
clause.

> The list is open. A verifier is a small interface; the ones we ship are the first set, not the only set.

## 6. How do I know which metrics composition is right for my case?

**Start from what a wrong answer costs you, not from the metric list.**

If the risk is a wrong figure (finance, contracts, tables, dates), the
numeric verifier is the one that matters and it should be `required`; it
has no false positives to speak of, because a number is equal or it is not.
If the risk is a real fact taken from the wrong place (another company, year,
row or clause), state the scope of every request and give every passage its
provenance: the scope check fails such a figure. If the risk is a sentence that
says something the documents never said (support, legal, policy assistants),
add a judge.

Then measure what gets through. `groundlens measure` takes about fifty answers
your team labels without seeing the verdict and tells you, with an interval,
how many wrong answers your policy passed and what that costs. Before changing
the policy, `groundlens replay` shows how many past decisions would change.

Whatever you choose, write it in the policy file. The policy is where "which
verifiers, which thresholds, what happens when they disagree" lives, with a
version and a hash, so the answer to "why did this fail" is always "this
policy, this evidence".

## 7. What exactly is a policy?

Information provided in a YAML file. It names:
    - which verifiers are required, 
    - recommended, 
    - optional, 
    - fallback or forbidden, 
    - the minimum determinism class allowed to decide, 
    - how a contradiction, an unresolved claim or a disagreement between verifiers maps to `PASS`, `REVIEW` or `FAIL`, and, optionally, 
    - which regulatory control each outcome concerns,
    - and, if you want, the scope keys every request must carry, risk classes that always go to a person, how numbers are written and rounded, and one sentence on what `PASS` means for your application.

Two bundled policies ship with the package. Write your own with `Policy.from_yaml()`, from scratch or on top of a shipped one with `extends`, and print what it resolves to with `groundlens policy show my-policy.yaml --resolved`. The engine has no opinion about which policy is right, and it never decides without one.

## 8. What is in an evidence record, and who can verify it?

Hashes of the input (never the text itself, unless you choose to attach
it), the engine version, every verifier that ran with its
version and model hash, every piece of evidence with its score, confidence,
determinism class and receipt (source id, span and text), the policy id,
version and hash, the decision and its reasons, the regulatory mapping, the
hash of the previous record, and a signature: Ed25519 by default, or ECDSA
P-256 from AWS KMS, Azure Key Vault or an HSM.

Anyone with the file and `pip install groundlens` can verify it, offline:
`groundlens record verify records.jsonl` recomputes every hash, every link
and every signature. The public key travels inside the record.

## 9. Does my data leave my machine or local deployment?

No. The engine makes no network calls, has no telemetry and no runtime
dependencies, and a CI job fails the build if an HTTP or TLS library ever
reaches an engine crate. If you add a judge, the prompt goes to the client you
pass, to your own model, wherever you run it (vLLM or Ollama on your servers
keeps it inside). Signers and stores use the clients you pass too.

## 10. Which languages does it handle?

Numbers: English, Spanish, Catalan, German, French, Italian, Portuguese,
Dutch and Swiss formats, with short and long scale words (`billion` versus
`billón`). An ambiguous numeral such as `1.234` under an unknown locale
keeps both readings rather than guessing. The intent check reads questions in
English and Spanish. A judge reads whatever languages your model reads.

## 11. Can I add my own verifier?

The engine is built around that. A verifier implements one trait
(`input → evidence`) and declares its determinism class; the policy then
treats it like any built-in one. Rules in YAML are the way to do this today
without writing Rust; custom checks in Python are in the design.

## 12. Should I use an LLM-as-a-judge?

Yes, as a verifier, not as an oracle. In our measurements a strong judge was
the only general checker that caught a correct-looking figure from the wrong
row or clause. GroundLens sends your own model a fixed, versioned prompt with
the policy, the scope and the provenance of every passage, and records the
model that answered and the hashes of the prompt and the reply. Its agreement
resolves nothing; its doubts send the answer to review, or to fail if the
policy says so. The shipped policies forbid it; a policy that wants it says so.
A deployment that wants a fully reproducible chain simply never enables it.

## 13. How fast is it?

The exact checks take microseconds to milliseconds per answer, on CPU, with no
model to load. With a judge, the time is your model's.

## 14. Is groundlens 3.x still supported?

No. `proofread()`, the 3.x interface, was removed in 6.0 with the model it
needed. The 3.x tree stays at tag `v3.1.0` for reproducibility of published
numbers. Records written by any version since 4.0 still verify.

## 15. What is open source in this project?

The engine, the verifiers, the policy language, the record format and the
command line are Apache-2.0, and will stay so: the open-source engine is
how anyone can check our claims and how the record format earns trust. 
Verification at production scale is a commercial service: measurement on
your data, evidence packages for procurement and conformity files, policy
and regulatory mappings maintained for you, private deployment and
specialised verifiers implemented. It is built on this engine, not instead of it.
