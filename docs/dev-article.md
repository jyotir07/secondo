---
title: "SECONDO: a local-first baking planner I built for [FRIEND'S NAME]'s home bakery"
published: false
tags: hacktoberfest, opensource, ai, python
---

<!--
DRAFT. Before publishing, replace every [BRACKETED] placeholder with what actually happened.
Do not publish feedback, quotes or results the friend didn't actually give. If something didn't
happen yet (e.g. they haven't used it on real data), say so; the honest version is a fine story.
Delete this comment before publishing.
-->

*This is my submission for the Hacktoberfest 2026 **Build for a Friend** challenge. #hf26challenge*

## The friend and the problem

[FRIEND'S NAME / how you'd like to refer to them] runs [a home bakery / tiffin service / ...]
from [their home kitchen, city]. [One or two sentences about who they are and how long they've
been doing this, in their words if possible.]

Every evening they face the same question: **how much of each thing should I make tomorrow?**

[Describe their actual process. Where do orders arrive (WhatsApp, calls, Instagram DMs)? Where do
they write them down? How do they guess walk-in demand? What goes wrong when they guess wrong:
leftovers, wasted ingredients, sold-out items, late nights?]

> [Optional: a short quote from them describing the problem. Only use their real words.]

What they don't need is an enterprise forecasting tool, a dashboard full of metrics, or another
app that wants their customer list in somebody else's cloud.

## What I built

**SECONDO** turns sales history and messy customer messages into a daily baking plan that a
person reviews and approves.

1. **Understand.** Import past sales from a CSV, or paste a customer message like *"2 sourdough
   and half a dozen cinnamon rolls for Saturday, eggless please – Priya"*. Gemma, running
   locally, extracts the products, quantities, date, name and dietary notes, and you check them
   before saving.
2. **Predict.** TabPFN forecasts tomorrow's demand for each product. It is compared against a
   simple historical average in a backtest that only lets each model see the past.
3. **Decide.** A kitchen plan with a quantity per product and the *reason* for each number:
   the forecast, its likely range, what sold on recent same weekdays, and what's already
   pre-ordered.
4. **Act.** Edit, then approve or reject. Nothing is final until a person approves it, and
   approved plans are kept as a record.

[Embed screenshots from docs/screenshots/ or a short GIF of the demo.]

## Why open-source AI was necessary here, not just nice

- **Privacy.** Customer names, orders and dietary needs stay on [FRIEND]'s own computer. Gemma
  runs through Ollama locally, so messages are never sent to a cloud LLM.
- **Cost.** No API keys, no subscription, no per-message billing. A small business can run it
  indefinitely for free.
- **The right model for the job.** Small-business sales history is a tiny tabular dataset.
  TabPFN is an open-weight tabular foundation model that works well on exactly that kind of
  small data without per-business training pipelines.
- **Ownership.** One SQLite file plus a JSON export button. If SECONDO disappears tomorrow, the
  data doesn't.

Can it run offline? After the one-time model downloads (TabPFN weights, and `gemma3:4b` via
Ollama), yes: everything runs on a laptop CPU.

## How it works (briefly)

- **FastAPI + SQLite** backend as a small modular monolith; **Next.js** dashboard.
- **Gemma never gets the final say.** It returns JSON constrained by a schema, the output is
  validated, and products are matched against the real menu by deterministic code, so the model
  can't book something the bakery doesn't sell. Dates are resolved in code from the phrase the
  model quotes ("Saturday"), because small models are unreliable at weekday arithmetic. If
  Ollama isn't running, a rule-based parser takes over, and the UI says so.
- **TabPFN** gets one row per (day, product) with lagged sales and weekday features. Every
  feature is computed only from earlier days, and tests check that a row never sees its own
  sales.

## Results, honestly

On the bundled **synthetic** dataset (not [FRIEND]'s data), over a 14-day backtest:

| Method | MAE | WAPE |
|---|---|---|
| Historical average (baseline) | 5.95 | 29.6% |
| Weekday average | 3.63 | 18.1% |
| TabPFN v2 | 3.42 | 17.0% |

TabPFN clearly beats the naive baseline and is slightly better than a weekday average. The
synthetic data was generated from weekday patterns, so this proves the pipeline works and isn't
leaking. It doesn't prove anything about a real bakery.

**On [FRIEND]'s real data:** [Fill in ONLY if this actually happened: how many weeks of history,
the measured MAE vs baseline from the Forecast page, and what it means in units of bread.
If it hasn't happened yet, say: "I haven't run it on their real data yet. That's the next step."]

## What changed for [FRIEND]

[Fill in only what really happened. Examples of things to report if true: they tried it for
N evenings; which part they used most; what they edited in the plan and why; anything that
confused them; whether it saved time or reduced leftovers, with numbers only if they were
actually measured. If they haven't used it yet, say so plainly.]

> [Their real reaction, quoted with permission. Leave this out rather than paraphrasing.]

## What I'd do next

- Run it on [FRIEND]'s real sales and report the real accuracy.
- Verify the Gemma path with live Ollama on their machine and measure extraction accuracy on
  real, anonymised messages.
- Track ingredients on hand so the plan can suggest restocks instead of just totals.

## Try it

- Source code: [REPO URL]
- Demo video: [LINK]
- Setup takes about five minutes: see the README. No API keys needed.

Thanks to [FRIEND] for [what they actually contributed: their time, their notebooks, their
patience with the first version].
