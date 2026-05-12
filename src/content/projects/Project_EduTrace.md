  ---

  ## Project Overview

  **EduTrace** is a clinical-grade evaluation platform that lets special-education evaluators
  draft, score, finalize, and export structured assessments for students with diagnoses such as
  ASD, ADHD, SLD, ID/DD, SI, OHI, and ED. The product spans a React Native mobile app, a Vite
  marketing site at `edutrace.net`, a Supabase backend (Postgres + Storage + Auth + Edge
  Functions), and an admin review workflow for evaluator onboarding.

  I am the sole owner across **product strategy, UX, technical architecture, implementation,
  DevOps, App Store operations, infrastructure, and customer-facing communication.**

  - **Target market:** licensed Turkish special-education evaluators (KVKK-aware data handling)
  - **Form factor:** native mobile (iOS / Android via Expo SDK 54) + responsive web landing
  - **Distribution:** EAS Build + App Store Connect; web deployed to verified domain `edutrace.net`
  - **Stage:** functional product with 15 shipped milestones (M1 → M15), live AI study-plan
    generation, admin onboarding flow, and a verified email + support pipeline

  ---

  ## Tech Stack

  ### Mobile (`/`)
  | Layer | Choice | Rationale |
  |---|---|---|
  | Framework | **Expo SDK 54** + **React Native 0.81.5** + **TypeScript** | Single codebase iOS/Android; SDK gives EAS Build + OTA + native modules |
  | UI System | **NativeWind v4** (Tailwind on RN) + custom Bento primitives | Utility-first styling with brand-consistent rounded cards, slate palette, soft shadows |
  | Routing | **Expo Router** (file-based) | Stack-based, deep-linkable, predictable layout-group composition |
  | State / Data | **TanStack Query v5** | Cache, invalidation, retries, optimistic UX |
  | Backend | **Supabase** (Postgres + RLS + Storage + Edge Functions + Realtime) | Managed Postgres with row-level security; cheaper + more flexible than Firebase for
  clinical schemas |
  | i18n | **i18next + react-i18next + expo-localization** | Full EN/TR, device-locale-aware, manual override persisted |
  | Offline | `@react-native-community/netinfo` + AsyncStorage queue | Evaluations editable offline; auto-sync on reconnect |
  | Audio | **expo-audio** (post-migration from `expo-av`) | Pause/resume in a single take, custom scrubber, playback speed control |
  | PDF | **expo-print** + **expo-sharing** + new **expo-file-system `File`/`Paths`** class API | Locale-aware finalized-evaluation reports, shared via native sheet +
  uploaded to Storage |
  | AI | OpenRouter (REST) + Direct Gemini (`@google/generative-ai`) | Provider toggle, exponential backoff with jitter, model fallback chain |

  ### Web (`/web`)
  - **Vite + React 19 + Tailwind CSS** standalone bundle (not an npm workspace — intentional)
  - **Hand-rolled i18n context** (~85 lines) — no i18next dependency, ~250 keys, EN/TR parity
  - Deployed to `edutrace.net` (verified domain, also used as the Resend sender domain)

  ### Backend
  - **Postgres** schema with row-level security on every table (`students`, `sessions`, `profiles`,
    `templates`, `study_plans`, `audit_logs`)
  - **Storage buckets** with bucket-specific RLS: public `student-photos`, `evaluation-memos`,
    `evaluation-reports`; private `verification-documents`
  - **Edge Functions** (Deno runtime) — `send-support-ticket` integrates with Resend for
    authenticated, JWT-validated support email with reliable Reply-To header handling
  - **Realtime** channels for live profile-status updates and admin-queue invalidation

  ---
  
  ## Business & Operational Ownership

  I operate this product the way a small founder team would — every non-coding lever is on me.

  ### App Store / Distribution
  - **App Store Connect** account: app record, screenshots, metadata, pricing, in-app messaging,
    TestFlight provisioning, and the iOS submission workflow
  - **`app.json` production configuration**: bundle identifiers, build numbers (currently 6,
    auto-incremented across submissions), splash screen, adaptive icon, scheme, locale config
  - **EAS Build** pipelines configured for `development`, `preview`, and `production` profiles —
    each with environment-variable wiring (e.g. `NPM_CONFIG_LEGACY_PEER_DEPS=true`) to keep CI
    green across React/Babel ecosystem drift
  - **iOS build & submission** managed end-to-end: provisioning, certificates, app-icon
    pipeline (1024×1024 RGB no-alpha to satisfy Apple's rejection rules), TestFlight, review

  ### Infrastructure & Vendor Management
  - **Domain ownership:** `edutrace.net` registered, DNS configured, verified with Resend for
    authenticated outbound email (SPF/DKIM/DMARC records owned and maintained)
  - **Supabase** project administration: schema migrations, RLS policies, Storage policy
    hand-configuration via dashboard (after discovering the project role can't own `storage.objects`),
    Edge Function deploys, function secrets, security-advisor reviews
  - **Resend** email vendor: API key management, support inbox routing to `aunsal89@gmail.com`,
    Reply-To header injection investigation/fix when Gmail intermittently ignored the JSON field

  ### Product / UX
  - **Designed the entire UX** for a non-technical clinical demographic: large touch targets,
    bilingual labels at the point of use, smart input (DOB auto-hyphenation with calendar
    validation), Bento card layouts with predictable 16pt rhythm, skeleton loaders that match
    final layout footprint, and a custom audio scrubber so an evaluator can review a voice memo
    without learning new gestures
  - **Bilingual content design**: every clinical template label, every domain name, every
    five-step rubric is authored in **both English and Turkish** in a structured JSONB schema —
    not retrofitted, but a first-class design decision
  - **Brand identity** designed from scratch: SVG-sourced rounded-square mark with three white
    "E" bars and an amber "trace dot" accent; build-time icon pipeline rasterizes one source into
    app icon, adaptive icon, splash, and favicon across iOS + Android constraints

  ### Compliance & Customer Trust
  - KVKK-aware data handling (Turkish GDPR-equivalent): admin-reviewed evaluator onboarding with
    government ID + diploma + selfie verification before any clinical data access is granted;
    private-bucket signed URLs (5-min TTL) for sensitive documents; per-user RLS scoping; account-
    switch cache wipe prevents cross-tenant data leakage

  ---
  
  ## Key Technical Achievements

  ### Architected an offline-first clinical workflow with conflict-free auto-save
  Built a synchronized tracking system in which evaluations auto-save every 30 seconds locally,
  queue mutations under `save_draft / finalize / update_completed` types, dedupe by `type+sessionId`
  so rapid auto-saves don't bloat the queue, and **flush the queue on network restoration**.
  Result: evaluators can work in clinic environments with unreliable Wi-Fi without losing data
  or duplicating sessions.

  ### Designed a JSON-driven dynamic template system (M9)
  Migrated evaluation templates from hard-coded TypeScript to a `templates.definition JSONB +
  version TEXT` schema in Postgres, with a 3-tier fallback resolver (remote → bundled JSON →
  hard-coded default) and an offline-cached `useTemplates` hook. Result: **non-developer
  template updates** are possible by editing JSON in the Supabase dashboard — no app release
  required for a new rubric question.

  ### Built a fully bilingual template-content pipeline (Option A)
  Designed a `LocalizedString = string | { en: string; tr: string }` discriminated type and a
  `resolveLabel(field, language)` helper threaded through every render site (form, task input,
  template picker, PDF export). Result: a single JSON definition produces both English and
  Turkish clinical reports with correct month names, label resolution, and step-scale wording —
  no parallel template files.

  ### Engineered a robust AI study-plan engine with provider fallback (M11/M12)
  Implemented dual-provider AI (OpenRouter REST + Direct Gemini SDK) with **per-attempt
  exponential backoff with jitter** (1s → 2s → 4s + ≤250ms), an OpenRouter **model fallback
  chain** of up to 10 models (`EXPO_PUBLIC_AI_MODEL` + `_1..9`, deduped + priority-ordered), a
  classifier that distinguishes transient errors (404/429/503/empty) from hard failures (auth/
  quota/400/network), and an `isStale` derivation based on a canonical sorted-key JSON snapshot
  so auto-save churn doesn't trigger spurious regenerate prompts. Result: a 12-week clinical
  study plan with S.M.A.R.T. goals and per-block rationale that ships even when an upstream
  model is rate-limited or offline.

  ### Solved silent file-upload corruption that had persisted for months
  Investigated a long-standing bug where voice memos and verification documents appeared to
  upload but were 0 bytes on the server. Root cause: `fetch(file://).blob()` silently produces
  empty blobs on React Native. Replaced with the **`expo-file-system` `new File(uri).bytes()`
  class API** across `evaluationService.uploadVoiceMemo` and `profileService.uploadVerificationDoc`.
  Result: data integrity restored for every binary asset in the app.

  ### Eliminated a multi-tenant cache leak on account switch (M15)
  Identified and fixed a critical UX bug where signing out user A and signing in user B briefly
  showed user A's students and stats. Two root causes — a 5-minute TanStack Query `staleTime` and
  a globally-keyed AsyncStorage students cache — both bypassed normal refetch logic. Implemented
  identity-change detection in `AuthContext` (via a `lastUserIdRef` that correctly ignores
  token-refresh events with the same id) that fires `queryClient.clear()` + a new
  `offlineStorage.clearUserScopedCaches()` on every transition. Result: zero cross-tenant data
  leakage; language and AI-provider preferences are intentionally preserved.

  ### Built an admin onboarding & review workflow with realtime updates (M13)
  Architected a `profiles.status` state machine (`pending → approved | rejected`) with a
  sequential 3-step document-capture flow (gov-ID back-cam → diploma back-cam → selfie front-cam),
  private Supabase Storage backed by signed URLs with 5-minute TTL, and **realtime channels with
  per-instance `useId()` topic suffixes** to avoid Supabase's "cannot add postgres_changes
  callbacks after subscribe()" crash. Admins see live queue updates without polling; approved
  users land in the main app the moment the badge flips, again without polling.

  ### Productionized email OTP + support pipeline via a Deno Edge Function (M14)
  Wired Supabase Auth email confirmation (OTP, 8-digit) with cool-down resend, a
  verify-email screen with auto-focus large-tracking input, and recovery routing from the login
  screen when `email_not_confirmed` is detected. Deployed a JWT-validated Edge Function that
  re-derives the caller identity via `supabase.auth.getUser()`, HTML-escapes inputs, and posts
  to Resend with **dual Reply-To injection** (JSON field + raw header) after diagnosing Gmail's
  inconsistent honoring of the JSON-only path.

  ### Resolved a high-stakes EAS Build / React-version invariant crash (2026-05-09)
  Diagnosed and reversed a React `19.1.0 → 19.2.6` bump that had silenced an EAS `ERESOLVE`
  during `npm ci` but **crashed the app on device** with React Native's
  `"Incompatible React versions"` invariant — because RN 0.81.5 ships its renderer compiled
  against React 19.1.0 with that exact version baked in. Documented a hard rule against bumping
  React above the SDK baseline, identified the legitimate fix (`.npmrc` + `eas.json` env mirrors
  for `legacy-peer-deps`), and separately resolved a Metro `@babel/runtime` resolution failure
  by adding it as a direct dependency. Result: clean builds, stable bundles, and an institutional
  guardrail in `CLAUDE.md` to prevent future agents from repeating the mistake.

  ### Designed and implemented a brand-grade icon & UI system (M15)
  Built three reusable UI primitives (`BentoCard`, `StatCard`, `Skeleton` with pulse animation
  via core RN `Animated` — deliberately avoiding Reanimated's worklet path on SDK 54), a
  react-native-svg `Logo` component, and a **build-time icon pipeline** (`npm run icons` via
  `sharp@^0.34.5`) that rasterizes a single SVG source into iOS-compliant RGB no-alpha icons,
  Android adaptive icons with proper safe-zone padding inside a brand-blue plate, splash assets,
  and favicons.

  ### Implemented a Metro resolver shim for react-native-reanimated v4
  Wrote a custom `resolveRequest` in `metro.config.js` (applied before `withNativeWind` wraps the
  resolver) to redirect Reanimated's `package.json` `"react-native"` field from TypeScript source
  to the compiled `lib/module/index.js`, fixing a hard runtime failure. Documented this in
  `CLAUDE.md` so it survives future config rewrites.

  ### Built a comprehensive PDF export pipeline
  Authored `buildReportHtml(params)` — a pure, locale-aware template that consumes both English
  and Turkish content, falls back gracefully via `resolveLabel`, and is rendered by `expo-print`
  into a sharable PDF that is also uploaded to a Storage bucket with `Date.now()` appended to
  the filename to avoid collisions on re-export.

  ---
  
  ## Architectural Principles I Enforce

  These aren't documented retroactively — they're written into `CLAUDE.md` as project law and
  are followed by every contributor (human or AI):

  - **Hooks call services; screens call hooks** — never the other way around
  - **Static data lives in `src/constants/data/`**, never inline in components
  - **Components > 200 lines** must be decomposed into hooks + sub-components
  - **All Supabase calls** route through `src/lib/supabase.ts`
  - **All UI strings** route through `t()` — zero hardcoded English in JSX
  - **RLS on every new table** — Storage RLS hand-configured via dashboard, not migrations
  - **Realtime channel topics** carry a per-instance `useId()` suffix to prevent registry collisions
  - **Type generation** is automated post-migration via the Supabase MCP — never edited by hand

  ---

  ## Selected Milestones (Shipped)

  | Milestone | Scope | Impact |
  |---|---|---|
  | M9 / M9g | Dynamic JSONB templates + bilingual parity across 6 templates | Non-dev template updates; full EN/TR clinical content |
  | M10 | Voice memo recorder rebuild (clip-based, pause/resume, custom scrubber, speed control) | Fixed silent 0-byte upload bug, restored data integrity |
  | M11 / M12 | AI study plans with dual provider, backoff, and model fallback chain | Reliable AI feature even under rate-limiting |
  | M13 | Admin review of evaluator signups with realtime + private signed URLs | KVKK-aligned onboarding gating |
  | M14 | Email OTP verification + Resend-backed support form via Deno Edge Function | Verified user accounts + working customer feedback loop |
  | M15 | Bento UI system + brand mark + critical multi-tenant cache wipe | Production-grade visual identity + closed a serious data-leak class of bugs |
  | M16 | Vite + React + Tailwind landing site at `edutrace.net` with hand-rolled EN/TR i18n | Marketing surface independent of mobile bundle weight |

  ---

  ## What This Demonstrates

  - **End-to-end product ownership** — vision, architecture, code, infra, brand, App Store, support
  - **Senior-level diagnostic depth** — root-causing React-renderer invariants, Metro resolver
    quirks, RN audio-session bridge edge cases, and Postgres audit triggers under data migrations
  - **Discipline around clinical-grade reliability** — RLS everywhere, identity-aware cache
    teardown, signed URLs for private data, schema-driven bilingual content
  - **Pragmatic engineering trade-offs** — chose Vite + hand-rolled i18n over i18next for the
    8-component landing site; kept `/web` outside the npm workspace boundary to insulate web
    React from the RN renderer's exact-version invariant; preserved `expo-av` in `package.json`
    as a transitive dep without re-importing it
  - **Operational maturity** — durable guardrails (`.npmrc`, `eas.json` env mirrors, `CLAUDE.md`
    hard rules) instead of repeated firefighting; every regression I've shipped has a written
    explanation of *why* and a rule that prevents recurrence