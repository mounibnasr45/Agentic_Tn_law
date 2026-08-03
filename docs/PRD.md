# PRD — Tunisian Legal Intelligence Platform
**Working title:** *Mostachar* (placeholder — rename freely)
**Author:** Mounib Nasr · **Date:** 2026-07-14 · **Status:** Draft v1

---

## 1. One-liner

One legal-data platform, two products:

- **Prep (B2C, students):** the exam-prep operating system for مناظرة الدخول للمعهد الأعلى للمحاماة — centered on an **AI correction engine** that grades dissertations, commentaires d'arrêt and cas pratiques against the real Tunisian rubric in minutes instead of the week a prep center takes.
- **Counsel (B2B, lawyers):** a citation-grounded research wedge — searchable محكمة التعقيب jurisprudence and consolidated, amendment-tracked codes.

Both run on the same corpus, retrieval, and agent infrastructure already built in this repo.

## 2. Strategy: why two products, and how we avoid dying from it

Decision (2026-07-14): pursue students and lawyers **in parallel**. The known risk is shipping neither well. Mitigation is structural, not aspirational:

1. **One platform, two thin surfaces.** ~70% of engineering effort goes to the shared layer (corpus pipeline, consolidated codes, jurisprudence index, retrieval, eval). Prep and Counsel are each a UI + a handful of product-specific services on top.
2. **Asymmetric ambition.** Prep is the *full product bet* (correction engine, study loop, monetized). Counsel v1 is deliberately a *wedge*: search + grounded Q&A over jurisprudence and codes. No drafting suite, no case management, no billing tools in v1.
3. **Shared moat, one data team.** Every asset acquired for one product (codes, amendments, تعقيب rulings, doctrine) serves both. Data acquisition is a single roadmap.
4. **Pipeline effect.** Students who pass become lawyers who already trust the brand — Prep is Counsel's acquisition channel with a 1–3 year lag.

**Kill/scale criteria:** if by month 4 Counsel has <10 weekly-active lawyers from pilot outreach, freeze it and go all-in on Prep for the exam season; revisit after. If Prep converts <2% free→paid by the season peak, the correction engine pricing/quality is wrong — fix before spending on growth.

## 3. Users

### Personas — Prep
- **P1 "المترشحة الجادة" (primary):** law graduate (maîtrise/licence en droit), 23–28, preparing for the ISPA concours (1st or 2nd year entry), often working part-time. Pays 800–2,500 TND for private prep centers or prepares alone with PDFs and Facebook groups. Biggest fears: méthodologie mistakes she can't see herself, no feedback on her writing, the oral.
- **P2 "المعيد" (repeat candidate):** failed once or twice; knows the material, needs targeted weakness repair and calibrated scoring, not more lectures.
- **P3 Prep-center owner (future B2B2C):** runs correction workshops; correction throughput is his bottleneck.

### Personas — Counsel
- **P4 "المحامي الشاب":** lawyer 0–7 years in, solo or small cabinet. Legal research today = paper collections, scattered PDFs, calling colleagues, Google. Needs: "أعطني قرارات تعقيبية في X" with real citations, and the current consolidated text of an article after amendments.
- **P5 Cabinet with associates (later):** multi-seat, document-heavy needs — out of scope v1.

## 4. Problems worth paying for

| # | User | Problem | Today's alternative | Why ChatGPT/Claude doesn't kill us |
|---|------|---------|--------------------|-----------------------------------|
| 1 | Student | No feedback on written méthodologie (تخطيط, إشكالية, structure) | Prep center: expensive, 1 correction/week | Generic LLMs don't know Tunisian rubrics, produce French-style plans, and have no calibration to real concours grading |
| 2 | Student | Must memorize code articles verbatim; laws change | Anki (no legal deck), rote reading | Requires a maintained, amendment-tracked article corpus — data, not model capability |
| 3 | Student | No idea where they stand vs. other candidates | Nothing | Requires a cohort — network effect, impossible for a general chatbot |
| 4 | Student | Oral exam terror; no way to rehearse | Friends role-playing | Needs jury-style behavior + Tunisian legal content + debrief rubric |
| 5 | Lawyer | Finding تعقيب jurisprudence on a point of law | Paper volumes, scattered PDFs, colleagues | The rulings aren't in any LLM's training set in usable form; grounding + citation is the product |
| 6 | Lawyer | Is this article's text current after amendments? | JORT archaeology | Consolidation is a data pipeline, not a prompt |

## 5. Product — Prep (student surface)

### 5.1 Centerpiece: the Correction Engine (P0)

The landing-page feature. "صحّح تحريرك في دقائق، بمقاييس المناظرة الحقيقية."

**Input:** typed text or photo upload of handwritten pages (OCR for Arabic/French legal handwriting — start typed-only if OCR quality blocks launch; photo is P1).

**Exercise types:** dissertation juridique · commentaire d'arrêt / تعليق على قرار · cas pratique / استشارة — in Arabic and French (concours subjects appear in both).

**Grading model:**
- A **rubric per exercise type**, encoding Tunisian conventions: مقدمة (تمهيد، تحديد الموضوع، الإشكالية، الإعلان عن التخطيط), تخطيط ثنائي with meaningful intitulés, correct citation of articles and jurisprudence, legal qualification quality, conclusion norms.
- **Calibration set:** real past subjects + graded model answers collected from prep professors and alumni (see §7 data plan). Every rubric version is evaluated against this set using the existing eval harness pattern; target: engine score within ±2/20 of human grader on ≥80% of calibration essays before launch.
- **Output:** overall score /20 + per-criterion breakdown + inline annotated feedback + "what a top-decile answer does here" exemplars + 2–3 concrete drills targeting the weakest criterion.

**Anti-gaming / trust:** every factual claim in feedback (articles, jurisprudence) must be retrieval-grounded with citation; show sources. A visible "هذا تقييم تقريبي معاير على مواضيع سابقة" honesty note — calibration transparency builds trust rather than eroding it.

### 5.2 Supporting loop (P0/P1)

| Feature | Priority | Notes |
|---|---|---|
| **Diagnostic test + weakness map** per matière | P0 | Feeds the plan; also the onboarding wow-moment |
| **Adaptive study plan** counting down to exam date | P1 | Re-plans when the student misses days |
| **Spaced repetition — code-article decks** | P0 | م.ا.ع، المجلة الجزائية، م.م.م.ت، المجلة التجارية… Cards auto-flagged when an amendment lands (shared pipeline §7) |
| **Timed mock exams + cohort percentile** | P1 | Real past-subject conditions; ranking unlocks once cohort ≥150 for a matière |
| **Annales explorer** (all past subjects + corrections) | P0 (free tier) | SEO/acquisition magnet; partially gated |
| **RAG legal Q&A assistant** (existing agent) | P0 (free, limited) | Demoted from "the product" to support layer; free-tier hook |
| **Mock oral exam (voice AI jury)** | P2 | Interrupting jury, follow-ups, debrief vs. oral rubric. Marketing gold; ship after written-exam season |

### 5.3 Explicit non-goals (Prep v1)
Video courses/lecture content (partner with prep centers instead of competing) · other concours (قضاء، عدول) until ISPA validates · mobile native apps (responsive web + PWA first).

## 6. Product — Counsel (lawyer surface, wedge only)

### 6.1 v1 scope (all P0, nothing else)
1. **Jurisprudence search:** natural-language + keyword search over محكمة التعقيب rulings (start with whatever corpus slice §7 secures first — even 5–10k rulings in 2–3 matières beats the status quo). Filters: chamber, year, matière. Every result links to the ruling text.
2. **Consolidated codes:** current text of any article with amendment history and JORT references. "نص المادة كما هو اليوم" is the trust anchor.
3. **Grounded research answers:** "ما هو موقف فقه القضاء من…" → answer with mandatory citations to rulings/articles in the corpus; refuses when the corpus can't support an answer. Zero tolerance for uncited claims — a hallucinated ruling kills the product with this audience.

### 6.2 Non-goals (Counsel v1)
Drafting (عرائض، عقود) · case/deadline management · client portals · multi-seat admin. All are Phase 2+ upsells once the wedge has daily usage.

### 6.3 GTM for the wedge
Design-partner motion: 10–20 young lawyers (recruited via ISPA alumni, bar association contacts, Facebook lawyer groups) get free access in exchange for weekly feedback and search-log review. No self-serve billing until retention is proven.

## 7. The shared platform (where the moat actually lives)

### 7.1 Corpus & data pipeline
Priority order of acquisition — each item states who consumes it:

| Asset | Prep | Counsel | Source / approach |
|---|---|---|---|
| Consolidated codes + amendment tracking | ✅ (decks, corrections) | ✅ (article lookup) | JORT + existing official PDFs; build an amendment-diff pipeline; this repo's ingestion is the seed |
| Past concours subjects (annales) ~2010→ | ✅ | — | ISPA publications, prep centers, alumni collection drive |
| Graded model answers + rubrics | ✅ (calibration) | — | **Paid partnerships with prep professors** — budget for this; it's the correction engine's fuel |
| محكمة التعقيب rulings | ✅ (commentaire practice) | ✅ (core) | Published bulletins (نشرية محكمة التعقيب), digitization + OCR; legal review of usage rights **before** launch |
| Oral-exam question bank | ✅ | — | Alumni interviews (structured debriefs each season) |
| Doctrine summaries | ✅ | ✅ | Licensed or original — later |

### 7.2 Technical architecture (maps to this repo)
- **Keep:** `app/` FastAPI service (JWT + refresh rotation), Postgres + pgvector hybrid retrieval, LangGraph agent (`app/agent/`), eval harness (`eval/`), Alembic migrations, Docker deploy.
- **Extend:**
  - Corpus schema: `documents` grows into typed entities — `article` (with `amended_by`, `valid_from`), `ruling` (chamber, date, number), `exam_subject`, `model_answer`, `rubric`.
  - **Correction service:** new `app/services/correction_service.py` — pipeline of structure-parse → rubric-criteria evaluation (LLM-as-judge with grounded retrieval per criterion) → score aggregation → annotation rendering. Each rubric criterion is an eval case; reuse the P3 harness pattern for calibration regression tests.
  - **SRS service:** deck generation from the article corpus; FSRS/SM-2 scheduling; amendment webhook flags stale cards.
  - **Multi-tenancy & products:** `product` claim in JWT (prep/counsel), per-product rate limits and entitlements.
  - **Payments:** Konnect or Paymee integration (webhook → entitlement grant); no Stripe in Tunisia.
  - **Arabic pipeline hardening:** embedding model must be evaluated on Arabic legal text (current eval harness extends naturally); BM25 needs Arabic normalization (تطبيع الهمزة/التاء المربوطة, diacritics stripping).
- **Frontend:** existing `frontend/` grows into the Prep web app; Counsel gets a separate minimal search UI sharing the design system.

## 8. Business model

### Prep — B2C freemium
- **Free:** annales explorer, limited RAG Q&A (N msgs/day), 1 correction as taster, diagnostic test.
- **Paid — "عدّة المناظرة":** ~49–69 TND/month, and a **season pass** (~249–349 TND until exam day — expect most revenue here given seasonality): unlimited corrections, full SRS decks, mocks + ranking, study plan; oral module as add-on or top tier.
- **Payments:** Konnect/Paymee/Flouci + e-dinar; investigate voucher-code distribution via bookstores/prep centers (cash is real in this market).
- **Later B2B2C:** prep-center licensing (correction throughput tool), per-student pricing.

### Counsel — B2B (post-validation)
Free for design partners → ~60–120 TND/month/seat once retention proven. Not monetized in v1.

## 9. Seasonality & GTM calendar (Prep)

The concours is typically announced by arrêté with exams in **autumn**; the prep intensity ramp is **June→September**. Working calendar (verify each season's dates against the official announcement):
- **Now→Sept (current season):** ship correction engine MVP + annales + SRS for 2–3 core matières; harvest this season's candidates even with a partial product — their essays are calibration data and their season is your best acquisition window.
- **Post-exam (Nov–Jan):** collect oral debriefs from those who pass to written stage; build oral module; Counsel design-partner push (team bandwidth frees up).
- **Spring:** results season → testimonial marketing ("نجحت مع…"), expand matières, prep-center partnerships for next cycle.

**Channels:** Facebook groups of ISPA candidates (the actual town square), law-faculty pages, TikTok/Reels short "correct my dissertation" demos, SEO on annales pages, prep-professor affiliates.

## 10. Success metrics

| Metric | Target (first season) |
|---|---|
| Correction engine calibration | ±2/20 vs. human on ≥80% of calibration set |
| Free signups (Prep) | 1,500 (≈ meaningful share of candidate pool) |
| Free→paid conversion | ≥5% by season peak (kill-line: 2%) |
| Weekly retention of paid users | ≥60% during season |
| Corrections per paid user per week | ≥3 (the habit metric) |
| Counsel design-partner WAU | ≥10 by month 4 (kill-line, §2) |
| North star (lagging) | Documented pass-rate delta of active users vs. base rate |

## 11. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Split focus across two products** | High | §2 structure: 70% shared platform, Counsel capped at wedge scope, explicit kill/scale criteria |
| Correction quality below trust bar | High | Calibration set + eval harness gating every rubric release; transparency note; human-in-loop review of low-confidence grades early on |
| Jurisprudence data rights / access | High | Legal review of نشرية usage before Counsel launch; start with unambiguously public material |
| Concours format/date changes yearly | Medium | Corpus tagged by session; rubrics versioned; watch the annual arrêté |
| Tiny TAM per season | Medium | Season-pass pricing captures value; multi-concours expansion (قضاء، عدول) is the designed v2; Counsel is the year-round revenue answer |
| Payment friction (no cards) | Medium | Konnect/Paymee day one; voucher codes via partners |
| Cloning by a prep center + dev | Low-Med | Moat = calibration data + cohort ranking network effect + amendment pipeline, none of which a clone gets from the model |
| Regulatory sensitivity (AI giving "legal advice") | Medium | Position as education (Prep) and research tool with citations (Counsel), never as legal advice; disclaimers; lawyer remains the professional of record |

## 12. Roadmap

**Phase 0 (weeks 1–4):** corpus schema + ingestion of consolidated core codes; collect ≥30 graded essays for calibration; rubric v1 for dissertation (Arabic first).
**Phase 1 (weeks 5–10) — Prep MVP:** correction engine (typed input, dissertation + cas pratique), annales explorer, SRS decks for 2 codes, freemium gating + Konnect. Launch to Facebook groups.
**Phase 2 (weeks 8–14, overlapping):** Counsel wedge with first jurisprudence slice + consolidated-article lookup; recruit 10–20 design partners.
**Phase 3 (season peak):** mocks + cohort ranking, commentaire d'arrêt support, photo/OCR input.
**Phase 4 (post-season):** oral exam voice module; Counsel retention verdict → monetize or freeze; begin قضاء concours corpus if Prep economics validated.

## 13. Open questions
1. Exact candidate counts per session (last 3 years) — needed to firm up TAM; source: ISPA announcements / bar association.
2. Legal status of redistributing نشرية محكمة التعقيب content — counsel opinion required.
3. Arabic handwriting OCR feasibility (candidate essays are handwritten in exam conditions) — spike early; determines photo-upload timeline.
4. Brand: one brand with two products, or separate brands for Prep vs. Counsel? (Lawyers may not want a "student tool" brand.)
5. Which 2–3 matières first for SRS + corrections? (Candidate-weighted: likely قانون مدني، قانون جزائي، إجراءات.)
