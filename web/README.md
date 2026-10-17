# Knockout web

The report page: Next.js (App Router), TypeScript, hand-written CSS, IBM Plex Sans and Mono through
`next/font` (self-hosted at build time).

```bash
pnpm install
cp .env.example .env.local      # NEXT_PUBLIC_API_URL, NEXT_PUBLIC_SENTRY_DSN
pnpm build && pnpm start        # http://localhost:3000
```

The API must allow the page's origin. `src/knockout/api.py` allows `http://localhost:3000` and any
`*.vercel.app`; add other origins with `KNOCKOUT_ALLOWED_ORIGINS`.

| Route                        | What                                                                           |
| ---------------------------- | ------------------------------------------------------------------------------ |
| `/`                          | One-line explanation, drug search, the eculizumab chain from public records    |
| `/drug/<name>`               | The report from `GET /api/drugs/<name>/report`, with trend, alerts, watchlist  |
| `/drug/eculizumab?fixture=1` | The development fixture, `fixtures/eculizumab.json`, labelled FIXTURE on screen |

The fixture is for working without the API. It is built from the engine's own run and the verified
live facts, says how in its `_fixture` note, and is never shown as a result.

## Screenshots

```bash
pnpm start &                     # with the API on :8000 for the live report
pnpm screenshots                 # home and eculizumab at 1440 and 390 px into screenshots/
THEMES=light,dark pnpm screenshots
node scripts/states.mjs          # the loading and API-unreachable states
```

## Design

- One accent, the amber of a medicine bottle, marks where the label or the reports agree with the
  genetics, and nothing else. Links, rules and type are ink on label stock.
- Verdicts are told apart by shape (filled, half, hollow, dashed square), so they read without
  colour: on the label, signal in reports, no signal, unknown.
- The label quote is set like the label: a boxed warning sits in a black rule box, verbatim, with
  the matched term marked.
- Report counts are shown as the 2 × 2 table the proportional reporting ratio is computed from,
  with the Evans criteria checked one by one.
