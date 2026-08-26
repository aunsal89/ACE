# CLAUDE.md — Portfolio Project Reference

A static, content-driven personal portfolio for **Ahmet Halit Ünsal**, deployed at **[ahmethalitunsal.com](https://www.ahmethalitunsal.com)**. Built with Astro + React (islands) + Tailwind v4. Content is authored as Markdown under `src/content/` and rendered through Astro content collections — every section on the page reads its body from a `.md` file so updates are content edits, not code changes.

---

## Stack

| Layer | Choice | Notes |
|---|---|---|
| Framework | **Astro 6** (`^6.3.1`) | Static `output: "static"`; single page (`/`) |
| Interactive islands | **React 19** (`^19.2.6`) via `@astrojs/react` | Only `VentureTabs.tsx` is interactive (`client:load`) |
| Styling | **Tailwind CSS v4** (`^4.3.0`) via `@tailwindcss/vite` | No `tailwind.config.js` — theme tokens live in `src/styles/global.css` under `@theme` |
| Typography | **@tailwindcss/typography** | Loaded as a v4 plugin in `global.css`: `@plugin "@tailwindcss/typography"` |
| Markdown | **marked** (`^18.0.3`) | Parsed at build time inside each `*.astro` component; rendered via `set:html` / `dangerouslySetInnerHTML` |
| TypeScript | strict (extends `astro/tsconfigs/strict`) | `jsx: react-jsx` |
| Node | `>=22.12.0` | from `package.json` engines |
| Hosting | **Vercel** | Domain via Namecheap DNS → Vercel |

---

## Commands

```bash
npm install        # install deps
npm run dev        # local dev server (Astro)
npm run build      # static build to dist/
npm run preview    # preview the built output
```

---

## Repository Layout

```
portfolio/
├── CLAUDE.md                  # Claude project reference
├── GEMINI.md                  # Gemini & overall system architecture reference
├── README.md                  # Portfolio summary & career engine reference
├── .env                       # Central credentials & API keys
├── web/                       # Astro 6 + React 19 Portfolio Frontend
│   ├── astro.config.mjs       # Astro + React + Tailwind plugin
│   ├── tsconfig.json          # strict + react-jsx
│   ├── package.json           # Node >=22.12.0
│   ├── public/
│   │   ├── ausnal_headshot.png # hero portrait
│   │   └── favicon.svg / .ico
│   └── src/
│       ├── content.config.ts  # registers cv / projects / skills collections
│       ├── styles/global.css  # Tailwind v4 entry + @theme tokens
│       ├── layouts/Layout.astro # <html>, fixed header, footer, slot
│       ├── pages/index.astro  # composes the single page
│       ├── components/        # Hero, Ventures, VentureTabs, Timeline, Education, Skills, Contact
│       └── content/
│           ├── cv/            # Intro.md, Experience.md, Education.md, Contact.md
│           ├── projects/      # Project_AURA.md, Project_EduTrace.md
│           └── skills/        # Toolbox.md
└── career-engine/             # Autonomous Career Engine Orchestrator
    ├── run.py                 # CLI executable entry point
    ├── config/                # config.yaml & tenants/aunsal/profile.yaml
    ├── data/                  # SQLite DB & dynamic model cache
    ├── deploy/systemd/        # systemd service & timer unit files
    ├── docs/                  # MULTI_TENANT_ARCHITECTURE.md
    ├── inbox/                 # Staged tailored CVs, Cover Letters & PDFs
    ├── src/                   # sourcing, scoring, applicator, database, notifications, utils
    └── tests/                 # 32 unit tests

---

## Content Collections

Defined in `web/src/content.config.ts`:

```ts
const projects = defineCollection({ loader: glob({ pattern: "**/*.md", base: "./src/content/projects" }) });
const cv       = defineCollection({ loader: glob({ pattern: "**/*.md", base: "./src/content/cv" }) });
const skills   = defineCollection({ loader: glob({ pattern: "**/*.md", base: "./src/content/skills" }) });
```

### ⚠️ Critical: Astro 6 glob loader lowercases entry ids

A file at `src/content/cv/Intro.md` is exposed as **`id: "intro"`**, not `"Intro"`. Every component that resolves an entry does so case-insensitively:

```ts
const intro = cv.find(e => e.id.toLowerCase() === 'intro');
```

Do not regress this to `e.id === 'Intro'` — `find()` will silently return `undefined` and the section will render with an empty body.

### Stripping the leading H1

Each markdown file starts with a `# Heading` so the file is also readable standalone. The components render their own section titles, so the leading H1 is stripped before parsing:

```ts
const body = (entry?.body || '').replace(/^#\s+.*\n+/, '');
const html = marked.parse(body) as string;
```

This pattern is used in `Hero`, `Timeline`, `Education`, and `Contact`. **`Skills.astro`** uses a different approach — `prose-headings:hidden` in the Tailwind class — because the toolbox is just a table.

---

## Page Composition

`src/pages/index.astro` composes the single page in this order, each wrapped with a decorative blurred-gradient background:

1. **Hero** — name, tagline, intro paragraph from `Intro.md`, headshot
2. **Ventures** — tabbed view of `projects/*.md` (React island)
3. **Timeline (Experience)** — `Experience.md` rendered with a custom timeline CSS treatment (dots + vertical line via `cv-timeline` class in `Timeline.astro`)
4. **Education** — `Education.md` in a centered card
5. **Skills** — `Toolbox.md` rendered as a styled table
6. **Contact** — `Contact.md` in a card at the bottom

### Header (in `Layout.astro`)

- Left: plain text `Ahmet Halit Ünsal` (no link — was previously a broken `A.H.Ü` → `#` anchor)
- Center: nav with anchors `#ventures #experience #education #skills`
- Right: GitHub icon, LinkedIn icon, **Contact button → `#contact`** (jumps to bottom; do **not** revert to `mailto:` — the Contact section is the source of truth for contact info)

---

## Styling Notes

- **Tailwind v4** is configured **entirely from CSS** (`src/styles/global.css`). No `tailwind.config.js` file. Theme tokens (`--color-brand-blue`, `--color-brand-amber`, `--color-bg-base`, etc.) are declared in `@theme { ... }`.
- The `@tailwindcss/typography` plugin is registered with `@plugin "@tailwindcss/typography"` — this is the v4-native way; do not add it to `astro.config.mjs`.
- Custom typography ramps (e.g. `prose-headings:hidden`, `prose-strong:text-amber-400`, `prose-p:text-xl`) are applied per section.
- `Timeline.astro` ships scoped global styles (`is:global`) for `.cv-timeline h3` to draw the timeline dot + vertical bar — these target the `h3` elements that come out of the markdown render, so renaming the H3 structure in `Experience.md` will break the timeline visual.

### Hero image cropping

The headshot uses `object-position: center 25%` (inline style on the `<img>`) so the face is visible. The image is full-height; centering crops the forehead.

---

## Editing the Site (Most Common Changes)

| Change | File |
|---|---|
| Profile paragraph in hero | `src/content/cv/Intro.md` |
| Add / edit a job | `src/content/cv/Experience.md` |
| Add / edit a degree | `src/content/cv/Education.md` |
| Update phone / email / location | `src/content/cv/Contact.md` |
| Update the skills table | `src/content/skills/Toolbox.md` |
| Add a venture | new `.md` in `src/content/projects/`, then update the title map in `VentureTabs.tsx` |
| Swap the headshot | replace `public/ausnal_headshot.png` |
| Theme colors / fonts | `--color-*` tokens in `src/styles/global.css` |
| Nav links / header layout | `src/layouts/Layout.astro` |
| Page order or new section | `src/pages/index.astro` |

---

## Adding a New Markdown-Driven Section

1. Add the markdown file under an existing collection (`src/content/cv|projects|skills/`), or create a new collection in `content.config.ts`.
2. Create a new component in `src/components/` that:
   - imports `getCollection` + `marked`
   - looks up the entry with `id.toLowerCase() === '<slug>'`
   - optionally strips the leading H1: `body.replace(/^#\s+.*\n+/, '')`
   - renders `marked.parse(body)` via `set:html`
3. Wrap the rendered content with `prose prose-invert prose-slate …` overrides for theming.
4. Import and place the component in `src/pages/index.astro`.
5. If it needs to be linkable from the nav, add an anchor link in `Layout.astro` and `id="..."` on the section root.

---

## Venture Tabs (the one React island)

`src/components/VentureTabs.tsx` is the only interactive component. It receives `projects: { id, body }[]` (where `body` is already-parsed HTML) from `Ventures.astro` and renders a tab strip. Tab labels are derived from `project.id`:

```ts
project.id === 'Project_AURA'     ? 'Project AURA' :
project.id === 'Project_EduTrace' ? 'EduTrace'     : project.id
```

**To add a new venture:** add a `.md` file in `src/content/projects/`, then extend the conditional above so its display label isn't the raw filename.

---

## Deployment

- Repo deploys to **Vercel** on push.
- Custom domain `ahmethalitunsal.com` (and `www.`) configured via Namecheap DNS → Vercel.
- Static output (`output: "static"`) — Vercel serves prebuilt HTML/CSS/JS; no server runtime needed.
- No environment variables required for build or runtime.

---

## Known Gotchas (Don't Repeat These)

1. **Glob loader id casing.** Astro 6's `glob` loader lowercases entry ids. A `find()` on the capitalized filename returns `undefined` and the section renders empty with **no build error**. Always compare with `id.toLowerCase()`.
2. **Duplicate H1.** Every markdown file leads with `# Title` so it reads cleanly standalone. Components that render their own `<h2>` must strip the leading H1 with the regex above, or the page shows the title twice.
3. **Tailwind v4 plugin syntax.** `@tailwindcss/typography` is loaded via `@plugin "@tailwindcss/typography"` in `global.css`, **not** via a `plugins: []` array in a JS config (there is no JS config).
4. **Header Contact button.** It must point to `#contact`, not `mailto:`. The Contact section at the bottom is the canonical contact surface; reverting breaks the documented UX.
5. **Timeline H3 styling.** The `Timeline.astro` global `<style>` block targets `.cv-timeline h3` to draw timeline dots. If `Experience.md` switches job titles from `###` to a different heading level, the timeline visual breaks.
6. **Hero image crop.** `object-position: center 25%` is intentional — do not change to `object-center` (cuts forehead) or `object-top` (cuts chin).
7. **Don't add LinkedIn/GitHub buttons to the Contact section.** Those icons live in the top-right header; duplicating them in the Contact card was explicitly removed.

---

## Conventions

- **Content over code.** Visible copy belongs in `src/content/*.md`. Components should be presentation only.
- **One markdown file per logical section** keeps edits scoped and reviewable.
- **Strip H1 + render your own heading** in each component for consistent typography.
- **No client JS unless necessary.** Only `VentureTabs.tsx` uses `client:load`. Everything else is server-rendered Astro.
- **Tailwind tokens live in CSS.** Don't introduce a `tailwind.config.js` — extend `@theme` in `global.css` instead.
