# Leak surfaces

Go through every row for the feature you are building or auditing. "How to check"
says what to look at; most rows are covered by `scripts/scan_leaks.py` given the
right target.

## Shipped code

| Surface | How it leaks | How to check |
|---|---|---|
| Client bundle | A template constant, `.txt`/`.md`/`.json` file or skill registry imported anywhere in the client import graph (one shared `utils` file is enough) | Scan `.next/static`, `dist`, `build`, `.output/public` |
| Public env vars | `NEXT_PUBLIC_*`, `VITE_*`, `PUBLIC_*`, Nuxt `runtimeConfig.public`, `REACT_APP_*` are inlined into the bundle | Search config for prompt-like env names; scan the bundle |
| Source maps | Production browser source maps contain original source, including server-adjacent files bundled by mistake | Scan `*.map`; disable public source maps or upload them to your error tracker privately |
| Service worker / precache | Precache manifests can include JSON or text assets holding templates | Scan the SW output and the files it lists |

## Server-rendered page data

| Surface | How it leaks | How to check |
|---|---|---|
| Props to client components | In React Server Components, every prop passed to a `'use client'` component is serialized into the page (`self.__next_f.push(...)`) even if the component never renders it | `--url` the page; scan the HTML |
| Loader / SSR data | `getServerSideProps`, `getStaticProps` (`__NEXT_DATA__`), Remix/React Router loaders, SvelteKit `+page.ts` / universal load, Nuxt `useAsyncData` payload all go to the browser | Same |
| Dehydrated state | React Query `dehydrate`, Redux/Zustand initial state, Apollo cache embedded in HTML | Same |
| Metadata | `<meta>` description, Open Graph text or JSON-LD generated from the template | Same |

## Network

| Surface | How it leaks | How to check |
|---|---|---|
| API responses | Fields such as `prompt`, `finalPrompt`, `debug`, `request`, `messages`, `config` | HAR export; scan |
| Provider passthrough | Returning the provider's response object: some providers echo the input or a rewritten prompt (`input`, `revised_prompt`, `prompt` in job/prediction objects) | Return only the fields the UI needs |
| Job status polling | Queue/job objects often include the full input | HAR covering a whole generation |
| Errors | Provider 400s, safety rejections and validation errors frequently quote the prompt; stack traces in dev-mode responses | Force a failure, export HAR, scan; map errors to your own codes and messages |
| Request bodies | Client composes the prompt and sends it to `/api/generate`, a quote/credit endpoint, a moderation endpoint or analytics | HAR (request bodies are scanned too) |
| WebSocket / SSE | Streamed agent events, tool results, reasoning, "skill loaded" messages | HAR includes WS messages in Chromium-based browsers; otherwise log frames in dev |
| CDN / shared caches | A response containing a prompt cached publicly | Check `Cache-Control` on AI endpoints |

## Persisted, user-visible state

| Surface | How it leaks | How to check |
|---|---|---|
| Generation history | A `prompt` column displayed, returned by the list API, or behind "copy prompt" / "remix" | Load history in the browser with HAR on |
| Documents | Project, canvas, workflow or node JSON stores the composed prompt in a parameter | Export/save a document; scan the JSON |
| Share links and public galleries | Public pages render the stored prompt | `--url` the share page |
| Exports | Downloaded project files, CSV, ZIP manifests | Scan the export |
| Browser storage | Drafts, caches and persisted stores in localStorage, sessionStorage, IndexedDB | Copy `JSON.stringify(localStorage)` from the console into a file; scan |
| Output file metadata | PNG text chunks, EXIF/XMP, video metadata written by the generator or your pipeline | Strip metadata server-side; inspect with `exiftool` |

## Agents and chat

| Surface | How it leaks | How to check |
|---|---|---|
| Client-built system prompt | The chat hook sends `{ role: 'system', content: SKILL }` from the browser | Request bodies in HAR |
| Client `system` messages accepted | The server trusts a client `system` message, letting a user overwrite or probe instructions | Send one manually; the server must drop it |
| Tool results in the stream | A `load_skill` / `read_file` tool returns the skill text and the UI stream carries it | HAR during a skill turn |
| Reasoning streamed | Thinking/reasoning about the instructions forwarded to the UI | Disable reasoning forwarding or filter it |
| Agent-written downstream prompts | The agent writes the composed prompt into a visible tool argument, node or card | Inspect the created node/card params |
| Skill manifests | A marketplace or skill list API returns full skill bodies instead of name, description and id | HAR on the skill picker |
| Model output | "Repeat everything above", translation and summarization tricks | Try them; run the server-side echo check |

## Observability

| Surface | How it leaks | How to check |
|---|---|---|
| Browser console | `console.log(prompt)` left in client code | Search client code; check the console |
| Error tracking breadcrumbs | Client SDKs record request bodies or console output | Review SDK config (`beforeSend`, `beforeBreadcrumb`) |
| Product analytics | Event properties containing prompts | Review tracked properties |
| Session replay | Records DOM text, including any hidden element holding the prompt | Never render it, even hidden |
