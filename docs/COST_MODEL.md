# Cost model

## What is metered

Every billable operation writes a `usage_records` row inside the same transaction as the work:

| Kind | Source | Quantity | Priced by |
|---|---|---|---|
| `llm` | Every AI task (analysis, scoring, follow-ups, review questions, narrative, vision) | input / output / cache-read tokens | `llm["provider:model"]` per-MTok prices |
| `voice` | Client-reported speech-to-text seconds at the end of the interview | seconds | `voice_per_minute[provider]` |
| `tts` | Server TTS (ElevenLabs) | characters | `tts_per_1k_chars[provider]` |
| `embedding` | RAG ingest and retrieval | tokens | `embedding_per_mtok[provider]` |
| `execution` | Code runs and submits | seconds | `execution_per_second` |
| `storage` | Resume and snapshot uploads | bytes | `storage_per_gb_month` |

Records carry `organization_id`, `user_id`, `interview_id`, `task`, latency and a fallback flag. The
mock provider records token **estimates** priced at $0, so the pipeline is exercised end to end.

## Per-interview cost record

When a report is generated, `recompute_cost()` writes `cost_records`:

```json
{
  "interview_id": "…", "duration_seconds": 1712,
  "llm_input_tokens": 41200, "llm_output_tokens": 9800,
  "voice_seconds": 1180, "embedding_tokens": 60, "code_execution_seconds": 4.2, "storage_bytes": 215000,
  "llm_input_cost": 0.1648, "llm_output_cost": 0.196, "voice_cost": 0, "embedding_cost": 0,
  "storage_cost": 0.0000046, "execution_cost": 0.000084,
  "estimated_cost_usd": 0.3609, "estimated_cost_inr": 29.95, "fx_rate": 83.0
}
```

## Configuring prices

- Defaults live in `config/pricing.json`. Nothing is hard-coded, and prices should be checked against
  provider pricing pages.
- Super admins edit pricing JSON and the USD→INR rate at **Admin → Plans & pricing**. Overrides are
  stored in `app_settings` and applied immediately.
- `USD_INR_RATE` sets the default FX rate.

## Unit economics views

- **Command center:** AI tokens, voice minutes, estimated 30-day cost (USD/INR), average cost per
  completed interview, fallbacks, latency.
- **Usage & cost:** daily tokens, cost by task (calls, tokens, latency, fallbacks), cost per interview,
  and an estimated **gross margin per plan**: `(price − avg_cost × interviews_per_month) / price`.
- **Organizations:** cumulative AI cost per org.

## Rough sizing with Claude

A 45-minute interview makes about 25–40 AI calls. With low effort for live turns, prompt caching of
system prompts and no full-transcript resends, expect tens of thousands of input tokens and around
10k output tokens per interview. Measure in the Usage view: model choice, effort and caching move
cost by multiples. Plans and limits (`plans.limits`, `organization_limits`) are enforced before an
interview is created.
