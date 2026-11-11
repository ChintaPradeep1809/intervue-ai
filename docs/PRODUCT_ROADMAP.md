# Product roadmap

## Now (MVP — in this repository)

Candidate practice end to end, org templates and invite links with cohort analytics, super-admin
operations, the cost model, and demo mode. AWS Data Engineer (2 years) is the flagship configuration.

## Next (0–3 months)

- **Realtime voice:** a streaming STT/TTS provider (WebRTC) behind the existing `VoiceProvider`
  interface, for lower latency and natural barge-in without headphones.
- **Payments:** Stripe/Razorpay checkout bound to `plans` and `subscriptions`, with usage-based overage.
- **Scale-out:** Redis for the WebSocket hub, rate limiter and background jobs; pgvector for RAG.
- **Question quality:** LLM-generated questions reviewed by humans into the bank; per-org banks.
- **Candidate benchmarking:** percentile vs cohort and role, trends per topic over attempts.
- **Recruiter workflow:** shareable report links, comments, stage pipeline.

## Later (3–12 months)

- Multiple languages: Hindi and Telugu interviews (STT/TTS + prompts), multilingual reports
- AI interviewer avatars (video presence) with opt-in camera
- Coding contests and timed assessments for campus drives
- Proctoring with explicit consent, and anti-cheating signals (paste detection, focus changes)
- Interview recordings (opt-in) with timestamped evidence playback
- ATS integrations (Greenhouse, Lever, Workday), calendar scheduling
- Enterprise SSO (SAML/OIDC), SCIM, audit export, data residency
- Public API and webhooks; mobile app for practice

## Principles we keep

- AI assists, humans decide.
- Evidence or it didn't happen: every score traceable to what the candidate said or wrote.
- Consent-first data handling, nothing recorded silently.
- Runs without vendor lock-in: every provider sits behind an interface with a local fallback.
