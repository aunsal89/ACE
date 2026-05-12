# EduTrace

**[edutrace.net](https://edutrace.net)** — a clinical-grade special-education evaluation platform for licensed Turkish evaluators, covering diagnoses including ASD, ADHD, SLD, ID/DD, SI, OHI, and ED.

I own 100% of product strategy, UX, architecture, implementation, DevOps, App Store operations, infrastructure, compliance, and customer-facing communication.

---

## What I Built

- **Offline-first clinical workflow** — auto-saves every 30 seconds, queues typed mutations (`save_draft / finalize / update_completed`), deduplicates by `type + sessionId`, and flushes atomically on network restoration, enabling reliable operation in clinics with intermittent Wi-Fi.
- **JSON-driven dynamic templates** — migrated evaluation templates from hard-coded TypeScript to a Postgres JSONB schema with a 3-tier fallback resolver (remote → bundled → default). Non-developer template updates ship with no app release.
- **Fully bilingual content pipeline** — a `LocalizedString = string | { en, tr }` discriminated type threaded through every render and PDF export site produces both English and Turkish clinical reports from a single JSON definition.
- **AI study-plan engine** — OpenRouter + Direct Gemini with exponential backoff, a 10-model fallback chain, and a transient-vs-hard-failure classifier. Delivers 12-week S.M.A.R.T. study plans even under upstream rate-limiting.
- **Admin onboarding state machine** — `pending → approved | rejected` with private signed URLs (5-min TTL), sequential ID/diploma/selfie capture, and realtime channels for KVKK-compliant evaluator gating without polling.
- **Multi-tenant cache isolation** — identified and eliminated a cross-tenant data leak by firing `queryClient.clear()` + scoped-storage wipe on every identity transition in `AuthContext`.

---

## Ownership Beyond Code

- **App Store Connect** — app record, metadata, TestFlight, 6 production builds submitted across iterative releases.
- **Domain & email** — `edutrace.net` DNS, SPF/DKIM/DMARC, Resend-authenticated outbound, JWT-validated support pipeline.
- **Vendor stack** — Supabase project administration (RLS policies, Edge Functions, security-advisor reviews), Resend, OpenRouter, Google Gemini, EAS Build CI.
- **Brand & UX** — designed the mark, the rasterized icon pipeline, and a Bento UI system for a non-technical clinical demographic.

---

**Stack:** React Native (Expo SDK 54), TypeScript, Expo Router, TanStack Query v5, NativeWind v4, Supabase (Postgres + RLS + Edge Functions + Realtime + Storage), Vite, React 19, Deno, Resend, OpenRouter, Google Gemini, EAS Build/Submit.
