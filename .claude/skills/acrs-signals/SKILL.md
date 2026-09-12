---
name: acrs-signals
description: >
  Interpret the AI Citation Readiness Score (ACRS) — whether a generative system could quote a page
  as an answer and be comfortable attributing it. Covers the seven scored components, the two things
  deliberately not scored, and how to turn a low score into concrete content changes.
---

# Reading ACRS

ACRS asks one narrow question: **if an AI system wanted to quote this page as
the answer to something, could it, and would it attribute the claim?**

That is not "is this page good". A beautifully written page with no figures,
no date and no author scores badly here and deserves to — there is nothing in
it a model can safely lift.

Read `evidence.acrs` on the audit object. `acrs_score` is the composite;
`citation_probability` bands it LOW / MEDIUM / HIGH / VERY_HIGH.

## The seven components

| Component | Weight | Measures |
| --- | --- | --- |
| `fact_density` | 0.20 | Share of pages stating ≥2 checkable figures — percentages, sums, multipliers, quantities with units |
| `passage_extractability` | 0.18 | Share of prose that survives being lifted: 1-3 sentences, not opening with a back-reference |
| `source_attribution` | 0.15 | Pages linking out to a real source, excluding sitewide footer chrome |
| `author_transparency` | 0.15 | Pages with a detectable byline |
| `answer_independence` | 0.12 | Pages posing a question, or carrying a definition list or table |
| `entity_clarity` | 0.12 | Pages declaring the entity they are about |
| `temporal_signals` | 0.08 | Pages carrying a publication or modified date |

## What it deliberately does not measure

`not_measured` in the evidence names two things, and they are the two most
tempting to fake:

- **Factual accuracy.** Verifying a claim needs the world, not the markup.
- **Information gain** — whether the page says anything unavailable elsewhere.
  That needs a corpus to compare against.

Never estimate either. A page full of confident nonsense and a page full of
verified research score identically here, and saying so plainly is what keeps
the rest of the number trustworthy.

## Diagnosing a low score

The shape of the failure tells you the fix:

**High extractability, low fact density** — the classic marketing-site
profile. The prose is well-formed but says nothing checkable. This is the
pattern behind copy like *"we transform the future through transformative
creative technology"*: fluent, unquotable. The fix is not rewriting for
style, it is adding specifics — what was made, for whom, how long it took,
what it cost, what changed.

**Low author transparency** — usually the single biggest lever, and usually a
content decision rather than an engineering one. An article attributed to an
organisation rather than a named person is a weaker citation candidate.

**Low temporal signals** — undated pages read as potentially stale, which
makes a model reluctant to quote them for anything time-sensitive.

**Low source attribution** — the page asserts without pointing anywhere.
Note the metric ignores links that appear on most of the site, so a footer
social profile earns nothing; a genuine reference from one article does.

**Low passage extractability** — paragraphs are too long, or they open with
"This", "However", "It" and cannot stand alone. Splitting long paragraphs and
rewriting openers to name their subject fixes it cheaply.

## Recommending concretely

"Add proprietary statistics" is not actionable. "The services pages describe
outcomes with no numbers — add project counts, turnaround times, or measured
results for three of them" is. Name the pages and the specific gap.
