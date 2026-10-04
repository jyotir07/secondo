---
title: "SECONDO: a local-first baking planner for Sidd's café in Bangalore"
published: false
tags: hacktoberfest, opensource, ai, python
---

*This is my submission for the Hacktoberfest 2026 **Build for a Friend** challenge. #hf26challenge*

> **A note on Sidd.** Siddhant ("Sidd") is a composite. He stands for the owners of the small
> cafés I know around Bangalore, not one specific person, and nothing below is a quote from a
> real owner. The problem is real. The results section only reports what I actually measured.

## The friend and the problem

Sidd runs a small café in Bangalore: a counter, a few tables, an oven in the back, and a
display case he fills every morning with croissants, sourdough, cookies, cinnamon rolls, banana
bread, and a cake or two for anyone who has ordered ahead.

Every night he has to decide **how much of each thing to bake tomorrow.**

His inputs are scattered:

- **Pre-orders arrive as WhatsApp messages.** "2 sourdough and half a dozen cinnamon rolls for
  Saturday, eggless please – Priya." They sit between supplier messages and family groups, and
  he copies them into a notebook when he remembers to.
- **Walk-in demand lives in his head.** Weekends are busier, Mondays the café is closed, and the
  start of the month is good. He knows this the way every owner does, roughly.
- **Guessing wrong costs money either way.** Bake too much and butter, flour and his time go
  into stock that won't sell tomorrow. Bake too little and a regular leaves without their
  croissant.

The tools that solve this "properly" are built for chains: expensive, made for analysts, and
they want his sales and his customers' names in someone else's cloud. Sidd doesn't need a BI
dashboard. He needs a sensible number for each tray, and to know *why* it's that number.

## What I built

**SECONDO** turns sales history and messy customer messages into a daily baking plan that the
owner reviews and approves.

1. **Understand.** Import past sales from a CSV (the notebook-to-spreadsheet step), or paste a
   WhatsApp order. Gemma, running locally, pulls out the products, quantities, date, customer
   name and dietary notes ("eggless"), and Sidd checks the result before it's saved.
2. **Predict.** TabPFN forecasts tomorrow's demand for each item and is compared against a
   simple historical average in a backtest where each model only ever sees the past.
3. **Decide.** A kitchen plan with a quantity per item and the reason for it: the forecast, its
   likely range, what sold on the last few same weekdays, and what's already pre-ordered.
   Ingredient totals come with it.
4. **Act.** Sidd edits any number he disagrees with, then approves or rejects. Nothing is final
   until he says so, and approved plans are kept as a record of what was predicted and what he
   actually decided.

![Kitchen plan](https://raw.githubusercontent.com/jyotir07/secondo/main/docs/screenshots/plan.png)

## Why open-source AI was necessary here, not just nice

- **Privacy.** Customer names, orders and dietary needs stay on the café's own laptop. Gemma
  runs through Ollama locally, so a customer's message is never sent to a cloud LLM.
- **Cost.** No API keys, no subscription, no per-message billing. A one-counter café can run it
  for free indefinitely.
- **The right model for the job.** A café's sales history is a tiny table: a few months, a
  handful of products. TabPFN is an open-weight tabular foundation model built for exactly that
  kind of small data, with no per-business training pipeline.
- **Ownership.** All the data lives in one SQLite file, and there's an "Export all my data"
  button. If SECONDO disappeared tomorrow, the café's records wouldn't.

**Can it run offline?** Yes, after the one-time model downloads (TabPFN weights, and `gemma3:4b`
via Ollama). Everything runs on a laptop CPU, with no internet needed at 10 pm when the plan is
made.

## How it works (briefly)

- **FastAPI + SQLite** backend as a small modular monolith, with a **Next.js** dashboard.
- **Gemma never gets the final say.** It returns JSON constrained by a schema. The output is
  validated, and products are matched against the real menu by deterministic code, so the model
  can't book something the café doesn't sell. Dates are worked out in code from the phrase the
  model quotes ("Saturday"), because small models are unreliable at weekday arithmetic. If
  Ollama isn't running, a rule-based parser takes over, and the UI says so.
- **TabPFN** gets one row per (day, product) with lagged sales and weekday features. Every
  feature is computed only from earlier days, and tests check that a row never sees its own
  sales.

## Results, honestly

No café, including any real "Sidd", has run SECONDO on real sales yet. Everything below comes
from the **synthetic** four-month dataset bundled with the repo, over a 14-day backtest:

| Method | MAE (units/product/day) | WAPE |
|---|---|---|
| Historical average (baseline) | 5.95 | 29.6% |
| Weekday average | 3.63 | 18.1% |
| TabPFN v2 | 3.42 | 17.0% |

TabPFN clearly beats the naive baseline and is slightly better than a weekday average. The
synthetic data was generated from weekday patterns, so this shows the pipeline works and doesn't
leak future data. It says nothing yet about how much bread a real café would save. On a laptop
CPU, a cold backtest takes about 30 seconds and a next-day forecast about 10.

## What changes for someone like Sidd

The intended change is small and concrete:

- Pre-orders stop living in chat scroll-back. They become checked order lines that
  automatically count toward tomorrow's plan.
- The nightly guess becomes a suggested number with its reasoning attached, which he can
  overrule in one tap.
- Over time, the approved plans form a record of what was baked compared with what sold.

Whether this actually reduces leftovers or sell-outs can only be measured on a real café's data
over a few weeks, and that's the next step.

## What I'd do next

- Run it with a real café's sales history and report the measured accuracy against the baseline.
- Verify the Gemma path with live Ollama and measure extraction accuracy on real, anonymised
  WhatsApp orders.
- Track ingredients on hand, so the plan can suggest restocks instead of just totals.

## Try it

- Source code: https://github.com/jyotir07/secondo
- Live demo (synthetic data): https://secondo-web.onrender.com. It runs the lighter models; TabPFN and Gemma run locally.
- Demo video: [ADD LINK]
- Setup takes about five minutes with no API keys; see the README.
