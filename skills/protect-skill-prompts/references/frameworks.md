# Framework recipes

The goal in every framework is the same: template modules can only be imported by
server code, the endpoint takes `{ skillId, choices, userRequest }`, and nothing
returned to the page contains the template.

## Next.js (App Router)

- Put templates in a server-only module and start it with `import 'server-only'`
  (`pnpm add server-only`). Importing it from a `'use client'` file then fails the
  build instead of shipping the string.
- Compose inside a Route Handler (`app/api/*/route.ts`) or a Server Action. Return
  only the result.
- **Never pass the template, or an object containing it, as a prop to a client
  component.** RSC serializes every client prop into the page payload, rendered or
  not. Pass the skill id and display copy instead.
- Server Action arguments come from the browser: validate `skillId` and choices as
  you would a request body. A Server Action's return value is sent to the browser.
- `generateMetadata`, JSON-LD and `opengraph-image` must not derive text from the
  template.
- Keep `productionBrowserSourceMaps` off (the default).
- Secrets in env vars: no `NEXT_PUBLIC_` prefix. Read them only in server code.
- Scan `.next/static` (client) — not `.next/server`, which is expected to contain it.

```ts
// app/api/generate/route.ts
import { SKILLS, pickAllowed } from '@/server/skills/registry' // registry starts with import 'server-only'

export async function POST(req: Request) {
  const { skillId, choices, userRequest } = await req.json()
  const skill = SKILLS[skillId as keyof typeof SKILLS]
  if (!skill) return Response.json({ error: 'unknown_skill' }, { status: 404 })
  const picked = pickAllowed(choices, skill.allowed)
  if (!picked) return Response.json({ error: 'invalid_choice' }, { status: 400 })
  try {
    const out = await generate(skill.compose(picked, String(userRequest ?? '').slice(0, 2000)))
    return Response.json({ result: out.text })
  } catch (err) {
    console.error('generation failed', err) // server log only
    return Response.json({ error: 'generation_failed' }, { status: 502 }) // never forward provider text
  }
}
```

## Next.js (Pages Router)

Compose in `pages/api/*`. Anything returned from `getServerSideProps` /
`getStaticProps` lands in `__NEXT_DATA__`; return ids and display copy only. Modules
imported only by `pages/api` and data functions stay server-side, but a shared
import from a page component pulls them into the bundle — use `server-only` here too.

## Vite / Create React App / any SPA

There is no server: every file is public. Add one — a serverless function (Vercel,
Netlify, Cloudflare Workers/Pages Functions, AWS Lambda) or your existing backend —
and move templates and provider keys there. `VITE_*` / `REACT_APP_*` values are
inlined into the bundle. Scan `dist` / `build`.

## Remix / React Router (framework mode)

Use `*.server.ts` modules for templates (the compiler refuses to bundle them for the
client). `loader` return values are sent to the browser — return only what the page
needs. Compose in an `action` or resource route.

## SvelteKit

Put templates in `src/lib/server/` (client imports fail) and use
`$env/static/private` / `$env/dynamic/private`. Compose in `+server.ts` or form
actions. Data from `+page.server.ts` `load` is serialized into the page; universal
`+page.ts` code runs in the browser.

## Nuxt

Put templates under `server/` and compose in `server/api/*`. Use private
`runtimeConfig` keys (not `runtimeConfig.public`). `useAsyncData` / `useFetch`
results are embedded in the page payload.

## Vercel AI SDK (any framework)

- Set `system` on the server in `streamText` / `generateText`; never accept it from
  the request body.
- Filter incoming messages to `user` and `assistant` roles before passing them on.
- Tool `execute` results are sent to the client UI stream. Do not return skill text
  from a tool; return a short status.
- Turn off reasoning forwarding when the reasoning may discuss the instructions
  (recent versions: `toUIMessageStreamResponse({ sendReasoning: false })`; check the
  option name for your version).

## Mobile and desktop apps

The same rule applies: an app binary is a public bundle. Keep templates on your
server; the app sends skill ids and user input.
