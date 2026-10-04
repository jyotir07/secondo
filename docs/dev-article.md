---
title: "SECONDO: An Offline Baking Planner for My Friend's Café, Built on Gemma and TabPFN"
published: false
tags: hacktoberfest, opensource, ai, python
---

*This is a submission for the [Hacktoberfest Weekend Challenge: Build for a Friend](https://dev.to/challenges/hacktoberfest-weekend-2026-10-01)*

## What I Built

**SECONDO** is a local-first planning tool for very small food businesses: home bakers, tiffin services, one-counter cafés. It takes sales history and messy WhatsApp orders and turns them into a **daily baking plan**. The owner reviews it, edits it and approves it. Every number in the plan shows the reason behind it.

**Who it's for.** My friend Sidd runs a small café in Bangalore. Most pre-orders arrive on WhatsApp, and every evening Sidd has to decide how much of each item to prepare for the next day. In Sidd's words: *"I usually just look at the orders and estimate how much I need to prepare."*

That estimate depends on information scattered across several places:

- **Pre-orders are buried in WhatsApp.** A message like *"2 sourdough and half a dozen cinnamon rolls for Saturday, eggless please"* sits between supplier chats and family groups, and *"sometimes people change things at the last minute."*
- **Walk-in demand is a gut feeling.** Weekdays differ from weekends, and some days are just busier. The owner knows these patterns only roughly.
- **A wrong guess costs money either way.** Bake too much and butter, flour and hours of work go to waste. Bake too little and a regular walks out without their croissant.

Proper forecasting tools are built for chains. They're expensive, they're made for analysts, and they want a café's sales and its customers' names in someone else's cloud. What Sidd needs is a sensible number for each tray and the reason behind that number.

SECONDO works in four steps:

1. **Understand.** Import past sales from a CSV, with row-level validation and duplicate detection. Paste a WhatsApp order and **Gemma, running locally**, pulls out the products, quantities, date, customer and dietary notes. The owner checks the result before anything is saved.
2. **Predict.** **TabPFN** forecasts tomorrow's demand for each product, with an 80% range. It is compared against simple baselines in a backtest where no model ever sees the future.
3. **Decide.** A kitchen plan lists a quantity per item with its reasoning: the forecast, the range, recent same-weekday sales and pre-orders. It also includes warnings, dietary requests and ingredient totals.
4. **Act.** The owner changes any number they disagree with, then approves or rejects the plan. **Nothing is automatic.** The plan stays a draft until a person approves it.

![Kitchen plan](https://raw.githubusercontent.com/jyotir07/secondo/main/docs/screenshots/plan.png)

### What Sidd said

I showed SECONDO to Sidd and asked four questions.

> **What do you think of SECONDO?**
> "Honestly, this could be pretty useful. I usually just look at the orders and estimate how much I need to prepare. Having something organise that for me would save time, especially on busy days."

> **Would you actually use it?**
> "Yeah, if it's simple enough. I don't want to spend 20 minutes entering orders just to get a list of what I need to bake. If it can take my existing orders and make sense of them, that's where I'd find it useful."

> **What's the biggest issue?**
> "Probably getting the orders in. Most of them come through WhatsApp, and sometimes people change things at the last minute. I'd want to be able to correct something quickly."

> **What would make you trust its recommendations?**
> "If it tells me to make 15 croissants, I'd want to know why 15. Is it based on previous orders or just guessing? I'd rather have a number I can adjust than something that acts like it knows everything."

Some of these answers line up with design decisions SECONDO already makes. Others point to things it doesn't do yet:

- **"I'd want to know why 15."** Every line in the plan shows its reasoning: the forecast, its range, what sold on recent same weekdays and what's already pre-ordered. Sidd's question, "previous orders or just guessing?", is answered right next to the number.
- **"A number I can adjust."** Plans are drafts. The owner edits quantities and approves the plan, and the model never decides on its own.
- **"Take my existing orders and make sense of them."** That's the paste-a-WhatsApp-message flow. Gemma reads the message, and the owner confirms the result instead of typing it in.
- **"Correct something quickly" is a real gap.** Today an extracted order can be fixed before it's saved, and plan quantities can be changed. A *saved* order can't be edited or cancelled yet, so last-minute changes aren't handled well. That's the first thing on my list.
- **"I don't want to spend 20 minutes entering orders."** This sets the bar for the order flow. I haven't timed it with Sidd's real orders yet, and that's the next test.

## Demo

🔗 **Live demo (synthetic data):** https://secondo-web.onrender.com

Click **Load synthetic sample sales**, then try Orders → Forecast → Kitchen plan. The free Render instance sleeps when idle, so the first load can take up to a minute.

> Free hosting has 512 MB of RAM, which can't hold PyTorch or a 4B model. The hosted demo therefore uses the **weekday-average forecaster** and the **rule-based message parser** as fallbacks, and the UI labels which one is active. Gemma and TabPFN run in the local setup, which is the real product (see below).

<!-- Optional: {% embed YOUR_VIDEO_URL %} -->

| Orders | Forecast |
|---|---|
| ![Orders](https://raw.githubusercontent.com/jyotir07/secondo/main/docs/screenshots/orders.png) | ![Forecast](https://raw.githubusercontent.com/jyotir07/secondo/main/docs/screenshots/forecast.png) |

## Code

{% github jyotir07/secondo %}

Running it locally takes about five minutes and needs no API keys:

```bash
# Backend
cd backend
uv sync --extra tabpfn
uv run uvicorn app.main:create_app --factory --port 8000

# Frontend (second terminal)
cd frontend
npm install && npm run dev        # http://localhost:3000

# Optional: local Gemma for reading messages
ollama pull gemma3:4b
```

## How I Built It

SECONDO is a **modular monolith**: one FastAPI service and one Next.js dashboard. It has no queues and no microservices, because one café doesn't need them. In the local setup everything lives in a single SQLite file on the owner's laptop.

```
Browser ─► Next.js (:3000) ─/api/*─► FastAPI (:8000)
                                        │
   Ingestion ──── Extraction ──── Demand ──── Planning
   CSV + dedupe   Gemma/Ollama    TabPFN      explanations,
                  ↳ rules fallback ↳ baselines approve/reject
                                        │
                                  SQLite file
```

**The open-source AI it uses:**

- **Gemma 3 4B via Ollama** reads customer messages. It runs locally and has to return JSON that matches a schema. The output is checked with Pydantic, and if the JSON is malformed the call is retried. Gemma never gets the final say:
  - Products are matched against the real menu by **deterministic code**, so the model can't book something the café doesn't sell.
  - Dates are worked out in code from the phrase Gemma quotes ("Saturday"), because small models are unreliable at weekday arithmetic.
  - If Ollama isn't running, a rule-based parser takes over and the UI says so.
- **TabPFN v2**, an open-weight tabular foundation model, does the forecasting. A café's history is a *tiny* table: a few months and a handful of products. That's too little data for most ML to do well, and it's exactly the case TabPFN is built for. It needs no training pipeline for each business. It gets one row per (day, product) with lag and weekday features, and **every feature is computed only from earlier days**. Tests check that no row can see its own sales.

**Honest evaluation.** The evaluation is a rolling-origin backtest over the last 14 open days, using only the bundled **synthetic** data:

| Method | MAE (units/product/day) | WAPE |
|---|---|---|
| Historical average (baseline) | 5.95 | 29.6% |
| Weekday average | 3.63 | 18.1% |
| **TabPFN v2** (CPU) | **3.42** | **17.0%** |

TabPFN clearly beats the naive baseline and only slightly beats a weekday average. The synthetic data was *generated* from weekday patterns, so these results show the pipeline works and doesn't leak future data. They say nothing yet about how a real café would do. On a laptop CPU (i5-12500H), a cold backtest takes about 30 seconds and a next-day forecast about 10.

**Fallbacks are visible.** If Ollama is down, extraction drops to rules. If TabPFN is missing or crashes, forecasting drops to the weekday average. The API and the UI always say which path ran and why. There are 54 backend tests, covering the Gemma path against a mocked Ollama (malformed JSON, schema violations, timeouts, a missing model) and leakage checks on the backtest.

**Agent tracing with Sentry.** Each AI step is wrapped in a custom span: `secondo.extract` contains a `gen_ai.request` span for the Gemma call, recording the model, token counts and attempt number. Plan generation, the forecast backtest and each TabPFN run (`secondo.model.tabpfn`) get their own spans too. Gemma failures while Ollama is up, and TabPFN crashes, become Sentry issues instead of silent fallbacks. Sentry never receives the message text or customer names, and `send_default_pii` is off. The traces showed where the time goes: one real trace had plan generation at **22.3 s**, almost all of it three ~7 s TabPFN runs. Everything else in that plan generation took about a second, so TabPFN is clearly the thing to optimise.

![Plan-generation spans in Sentry](https://raw.githubusercontent.com/jyotir07/secondo/main/docs/screenshots/Sentry-ss.png)
*Every plan generation is recorded as a `secondo.plan.generate` span in Sentry.*

**Voice briefing with ElevenLabs.** An approved plan gets a **Play briefing** button, so the owner can hear the plan read aloud. The backend calls ElevenLabs, and the API key never reaches the browser. The text it sends contains only quantities, dietary labels and warnings, never customer names or notes, and the same text is shown on screen as a transcript. Audio is cached per plan. In testing, a 244-character briefing became about 23 seconds of MP3 in 8.7 s, and the cached replay took 0.05 s.

![Voice briefing](https://raw.githubusercontent.com/jyotir07/secondo/main/docs/screenshots/plan-briefing.png)

**MongoDB Atlas for the hosted demo.** Free Render disks are wiped on restart, so the hosted demo can't keep a SQLite file. `repository_mongo.py` implements the same `Repository` interface as the SQLite version and is used whenever `MONGODB_URI` is set, so no other code changes. Duplicate detection is enforced in the database itself by a unique index on `(business_id, dedupe_key)`. The full test suite also runs against a real Atlas cluster (56/56 passing), and an approved plan survived a backend restart.

**Stack:** Python 3.11, FastAPI, Pydantic, pandas, SQLite (uv) · Next.js 16, TypeScript, Tailwind 4, Recharts · Ollama + Gemma 3 4B · TabPFN v2 (CPU PyTorch). The hosted demo adds Render, MongoDB Atlas, Sentry and ElevenLabs.

## Why Does Open Innovation Matter?

For a one-counter café, open models are what make the product possible at all:

- **Customer data stays on the café's laptop.** Names, orders and dietary needs ("eggless", "nut allergy") are personal data about the owner's regulars. Gemma runs through a local Ollama server, so a customer's WhatsApp message is never sent to a cloud LLM. With a closed API, every order would leave the building.
- **It runs offline.** After the one-time model downloads, everything runs on a laptop CPU. Making the evening plan doesn't need an internet connection or a working API.
- **It costs nothing to run.** There are no API keys, no subscription and no per-message billing. A tiny business can use it indefinitely for free, which is the only price that works at this scale.
- **The right model for the data.** A closed general-purpose LLM is the wrong tool for forecasting four months of sales for six products. An open tabular foundation model like TabPFN fits that data, and I could inspect it, benchmark it honestly against baselines and run it locally.
- **Swappable and controllable.** The extraction model is a config value (`OLLAMA_MODEL`), and so is the forecaster (`FORECAST_PROVIDER`). If a better small open model comes out next month, switching is a one-line change. No vendor can deprecate it out from under the café.
- **Ownership.** All data lives in one SQLite file, and there's an **Export all my data** button. If SECONDO disappeared tomorrow, the café's records wouldn't go with it.

## My Agent Session

<!-- Paste your DevRelay agent_session embed here, or delete this section. -->

## Prize Categories

Best Use of Gemma · Best Use of TabPFN (Prior Labs) · Best Use of Render · Best Use of ElevenLabs · Best Use of MongoDB Atlas · Best Use of Sentry Agent Tracing

<!-- Thanks for participating! -->
