# AI architecture

## Principle: the model decides within boundaries

The LLM never drives the interview directly. `packages/interview-engine` owns an explicit state
machine and the deterministic business rules: time budgets, question counts, at most 2 follow-ups,
no repeated questions, difficulty adaptation and round transitions. AI is used for five **tasks**,
each with a Pydantic output schema:

| Task | Schema | Used for | Deterministic handler |
|---|---|---|---|
| `resume_analysis` | `ResumeAnalysis` | Skills (with verbatim evidence), gaps, priority topics, level, difficulty | Skill taxonomy + regex experience extraction |
| `personalize_question` | `PersonalizedQuestion` | Rephrase a bank question around a **verified** resume skill | Prefix "Your resume mentions X." |
| `score_answer` / `score_code` | `AnswerScore` | Category scores, covered/missing concepts, quoted evidence | Concept-keyword coverage, reasoning/trade-off/specificity signals, code heuristics + test results |
| `generate_followup` | `FollowUpDecision` | Clarification / challenge / edge case / optimization / architecture / behavioral | Score band → type; curated follow-ups by trigger; quotes only phrases the candidate said |
| `code_review_question` | `CodeReviewQuestion` | One question about the submitted code | Failing test → "walk me through", nested loops → complexity, SQL → optimization |
| `report_narrative` | `ReportNarrative` | Headline, summary, recommendations | Templates from computed aggregates |
| `screen_analysis` | `ScreenAnalysis` | Describe a consented snapshot (vision) | Dimensions only, labelled as mock |

## Provider abstraction (`packages/ai`)

```
AIClient(providers=[primary, fallback?])
   ├─ per-provider retries (2) with backoff, asyncio timeout
   ├─ non-retryable errors (auth, 400, refusal) skip to the next provider
   ├─ final fallback: deterministic handler for the same task (MockAIProvider)
   └─ on_usage callback → usage_records (tokens, latency, cost, fallback flag)
```

- `AnthropicProvider` uses the Messages API (`anthropic` SDK 1.x). It sends structured outputs
  (`output_config.format` with a JSON schema generated from the Pydantic model), sets `effort` per
  task (low for real-time interviewer turns, medium for analysis), and uses a cached system prompt.
  It enables server-side refusal fallbacks (`fallbacks: "default"`) and runs a bounded tool loop
  (≤3 rounds). Responses are re-validated with Pydantic; `stop_reason` `refusal` and `max_tokens`
  are handled explicitly.
- The default model is `claude-opus-5-5` (`AI_MODEL`). Set `AI_FALLBACK_MODEL` (e.g.
  `claude-sonnet-5-5`) to try a second model before the deterministic engine.
- `MockAIProvider` dispatches tasks to registered deterministic handlers. It makes the whole product
  run without keys and is the last-resort fallback in production.
- `EmbeddingProvider`: `HashingEmbeddingProvider` (384-dim signed feature hashing over unigrams and
  bigrams) is local, free and deterministic. Hosted embeddings plug in behind the same interface.
- `VoiceProvider` (server) and `VoiceProvider` (web client) are separate. The browser runs STT and TTS
  in real time; the server decides whether TTS is browser- or server-rendered (ElevenLabs).

## OpenAI provider

`OpenAIProvider` uses the **Responses API** (Chat Completions rejects function tools together with
reasoning effort on current reasoning models). Each call sends a strict JSON schema
(`text.format`), `reasoning.effort` per task and `store=False`. Reasoning items are replayed via
`reasoning.encrypted_content` across tool rounds. Usage (incl. cached input tokens) is metered and
priced from `config/pricing.json`.

## Free stack: Gemini + Edge voice

`ChatCompletionsProvider` (`AI_PROVIDER=gemini` or `openai_compat`) targets any OpenAI-compatible
Chat Completions endpoint. Gemini's endpoint accepts strict `response_format` JSON schemas together
with function tools and `reasoning_effort`. Assistant tool-call turns are replayed with their
provider extras, so Gemini's thought signatures survive the tool loop.

- **Free-tier behaviour:** demand spikes return 503. These are retried once, then the next model in
  the chain answers. Per-minute 429s pause that model for 60 s, and daily-quota 429s pause it for
  1 hour. **The free tier allows 20 requests per day per model**, and one interview uses about 15–25,
  so `AI_FALLBACK_MODEL` takes a comma-separated list and the chain rotates through every free model
  (about 5 interviews a day across 6 models). For real usage, enable billing on the Gemini project or
  use a provider with higher free limits.
- **Measured (Oct 2026, free tier):** 3.5-flash-lite ≈1–2 s (live follow-ups), 3.5-flash ≈2–4 s
  (scoring, analysis, report). 3.7-flash and 3.8-flash were often overloaded or took 10–25 s.
- **Data use:** Google may use free-tier prompts to improve its products. Use the paid tier (or
  another provider) before interviewing real candidates.
- **Edge voice** (`VOICE_PROVIDER=edge`) synthesises MP3 with Microsoft Edge neural voices through
  `edge-tts` (≈1.7–3 s per turn, no key). It uses Edge's public read-aloud endpoint, so treat it as
  a development and demo option; use a contracted TTS for production.

## Latency design

Measured on `gpt-6.1-sol`, an evaluation call takes 7–12 s, which is too slow to make the candidate wait. So:

- **Model routing:** `AI_FAST_MODEL` (e.g. `gpt-6-luna`) handles live turns: follow-ups,
  personalisation and code-review questions (≈2–5 s). `AI_MODEL` handles analysis, scoring and the
  report narrative.
- **Deferred scoring:** with a real LLM, the engine routes each answer on an instant deterministic
  score (difficulty and follow-up band). The LLM score is computed in the background and replaces the
  estimate; report generation waits for all pending refinements.
- **Circuit breaker:** quota or auth errors (no credits, invalid key) disable a provider for 5
  minutes instead of retrying every call. Turns fall straight through to the next provider or the
  deterministic engine, and the reason shows in the command center. Server TTS has the same 10-minute
  breaker and falls back to browser speech.

Measured end to end with OpenAI + ElevenLabs: about 3–4 s from answer to the interviewer starting
to speak, including TTS.

## Interviewer tools (`intervue_engine/tools.py`)

The tools exposed to the model are read-only: `get_candidate_profile`, `get_resume_analysis`,
`get_job_description`, `get_interview_state`, `get_previous_answers`, `get_current_code`,
`get_execution_result`, `analyze_screen_snapshot`. State-changing operations (`run_code`,
`run_sql`, `calculate_score`, `update_interview_state`, `generate_followup`, `complete_round`,
`generate_report`) are executed by the engine and orchestrator, so the model can't mutate state.

## Guardrails against fabrication

1. **Resume claims.** `verify_skills` keeps a model-claimed skill only if its evidence or an alias
   appears in the resume text. Personalised questions may reference only verified skills; otherwise
   the original question is used.
2. **Evidence.** `verify_evidence` keeps a quote only if, after normalisation, it is a substring of
   the claimed source (transcript, code or design). Dropping a quote lowers confidence.
3. **Measured facts.** Code correctness comes from test results, time management from timestamps,
   and report headline facts (strongest area, main weakness) from aggregates. The LLM writes only
   the prose.
4. **Context management.** The full transcript is not resent. The engine keeps a rolling
   `context_summary` of recent topics and scores; the model fetches older answers through
   `get_previous_answers` when it needs them.

## Adaptive follow-up logic

| Answer score | Follow-up type | Difficulty |
|---|---|---|
| "I don't know" / skip | none, move on | — |
| < 50 | clarification (on missing concepts; at most one) | ↓ |
| 50–79 | challenge / edge case (prefer triggers matching concepts the candidate mentioned) | = |
| ≥ 80 | optimization / architecture | ↑ |

A follow-up answer is scored against concepts that fit the follow-up type, not the base question, so
a candidate isn't penalised for not repeating what they already covered.

## RAG

Organization documents (guidelines, role descriptions, topics, question banks) are parsed, chunked
(~1,200 chars with overlap), embedded and stored in `knowledge_chunks`. When an org interview is
created, the top chunks for role + JD are appended to the job context, so the analysis and planner
prioritise the organization's topics. Retrieval can be tested from Settings → Knowledge base. At
scale, move embeddings to pgvector (`vector(384)` + HNSW) without changing the service interface.

## Prompting notes

System prompts are short and rule-based: neutral tone, one question at a time, never reveal answers,
and quote only verbatim. Inputs from candidates, resumes and JDs are wrapped in tags
(`<answer>`, `<resume>`, `<job_description>`) and treated as data. All prompts live next to their
task in the engine and evaluation packages.
