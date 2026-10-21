---
name: protect-skill-prompts
description: Keep proprietary prompts — skill templates, system prompts, agent instructions, few-shot examples, style recipes — out of the browser when building AI features, so users cannot copy them from DevTools, the JS bundle, network responses, page data or saved state, while still letting users steer results in their own words. Use whenever a web feature sends a prompt to an LLM, image, video or audio model, ships an AI "skill", preset, template or agent, or stores generation history; whenever someone says "don't expose the prompt", "hide the system prompt", "users can copy our prompt", "the prompt shows in the network tab", "protect our skill", "提示词不要暴露给前端", "防止用户复制提示词" or "skill 提示词泄露"; and to check or audit an existing chatbot, agent or AI feature for system-prompt or prompt leaks before launch ("does our chatbot leak its system prompt", "is our prompt exposed anywhere", "检查提示词有没有泄露").
---

# Protect skill prompts

**The browser is public.** Anything that reaches it — bundle, page data, network
responses, storage, errors, the model's own output — can be copied. A prompt is
protected only when it is composed and used on the server and never returned.
Minifying, base64, "encrypting" with a key the client holds, or hiding a component
while still sending its data protects nothing.

**Prevent leaks by design, not by redaction.** Replace provider errors with your own
message instead of scrubbing the prompt out of theirs; give tools arguments that only
carry user data instead of filtering a model-written prompt. Exact-match redaction misses
truncated quotes and paraphrases, and so does any scanner.

Protect the **template**, not the user. Hiding a template must never reduce what a
user can ask for: they keep a free-text field, and their words override the
template's defaults.

## 1. Separate the three kinds of data first

Before writing code, classify every value in the feature:

| Data | Example | Owner | Allowed where |
|---|---|---|---|
| **Template** (the secret) | system prompt, skill instructions, few-shot examples, style recipe, negative prompt, hidden model params | you | server only |
| **User choices** | style id, aspect ratio, number of people, language | user | anywhere |
| **User's own words** | "make the jacket red", an uploaded photo | user | anywhere |
| **Result** | text, image, video | user | anywhere — after an echo check (§5) |

**Compose late.** Template + choices + words are joined in memory, at the moment of
the provider call, on the server. Everything that is persisted or returned — history
rows, project/canvas documents, share links, exports, credit quotes, logs — holds only
the choices and the user's words, plus a template *id* and version.

## 2. Workflow

1. **Inventory.** List every secret string and the file it lives in. Note which
   client code currently imports, fetches, renders or stores it.
2. **Trace the leak surfaces.** Go through [references/leak-surfaces.md](references/leak-surfaces.md)
   for the feature. The usual misses are page data passed to client components,
   provider responses passed through verbatim, error messages, generation history,
   and agent tool results streamed to the chat UI.
3. **Move composition to the server** using a pattern from §3. Mark template modules
   server-only so a client import fails the build (framework recipes:
   [references/frameworks.md](references/frameworks.md)).
4. **Keep the user in control** (§4).
5. **Treat the model as a leak surface** (§5).
6. **Verify** with `scripts/scan_leaks.py` and a browser pass (§6). A change is not
   done until the scanner is clean on client-facing output *and* finds a deliberately
   planted fragment (the positive control).
7. **Report honestly** (§7): what is protected, what still can be inferred.

## 3. Patterns

### A. Skill-id endpoint (default for one-shot generation)

The client sends a reference, choices and words. The server owns the rest.

```ts
// server/skills/registry.ts  — server-only module
import 'server-only' // Next.js; use your framework's equivalent (see frameworks.md)

const SKILLS = {
  'product-stylist': {
    version: 3,
    allowed: { style: ['studio', 'outdoor', 'flatlay'] as const },
    compose: (c: { style: string }, userRequest: string) =>
      `${SECRET_TEMPLATE.replace('{style}', c.style)}\n\n` +
      `User request (takes priority over the defaults above): ${userRequest || 'none'}`,
  },
} as const
```

```ts
// POST /api/generate   body: { skillId, choices, userRequest }
const skill = SKILLS[body.skillId]                       // unknown id -> 404
const choices = pickAllowed(body.choices, skill.allowed) // reject values not in the allowlist
const prompt = skill.compose(choices, body.userRequest)  // composed here, never stored or returned
const out = await provider.generate({ prompt })
await db.history.insert({ skillId: body.skillId, version: skill.version, choices, userRequest: body.userRequest, resultUrl: out.url })
return Response.json({ resultUrl: out.url })             // no prompt, no provider passthrough
```

Re-running from history sends `{ skillId, choices, userRequest }` again; the server
recomposes. Quote and credit endpoints take the same body, never a prompt.

### B. Agent / chat with a hidden skill

- The client sends a **skill reference** plus the user's words (`{ skillId, text }` or
  a token like `/skill:product-stylist`). The server loads the skill into the system
  context; the UI renders a **badge** for the reference, not its text.
- The server builds the system prompt and **drops any client-supplied `system`
  messages** — otherwise a user can replace your instructions or confirm them.
- Tool results, "skill loaded" events and reasoning traces are streamed to most chat
  UIs. Filter anything containing skill text out of the stream, or never return it
  from a tool in the first place.
- If the agent produces a prompt for a downstream step (an image or video tool, a
  workflow node, a canvas card) and that prompt lands in a user-visible or editable
  field, the template has leaked through the agent. Give the downstream tool
  `{ skillId, choices, userRequest }` and compose on the server instead.

Details and code: [references/agents-and-chat.md](references/agents-and-chat.md).

### C. Node editors, canvases, pipelines

Node/document state is saved and shown to the user, so it is client data. A
"skill node" stores only choices and a user-request field; the server composes when
it runs the node. Price/quote calls take node params, not prompts. If the same node
type can also take a raw prompt, keep the hidden-template node a separate type so a
user cannot read the template by switching modes.

## 4. Keep the user in control

- Give every skill a visible **free-text request** field (or let the agent fill it from
  chat). It holds only the user's words.
- Place it in the composed prompt with an explicit priority rule ("the user's request
  overrides the defaults above"), so asking for a different outfit, framing or tone
  actually changes the result.
- Validate *choices* against an allowlist; do **not** restrict or rewrite the user's
  words to protect the template. Never describe "users can no longer change X" as a
  benefit of hiding a prompt.

## 5. The model is also a leak surface

Users can ask the model to "repeat everything above". You cannot fully prevent
extraction through outputs, but you can raise the cost:

- Tell the model in the template not to reveal or paraphrase its instructions.
- For text output, check it on the server before returning it: compare against the
  template with `scan_leaks.py`'s fingerprint approach (shared 8-word runs) and
  replace or refuse on a match. When streaming, hold back a small window so a match
  can be caught before it is sent.
- Image/video outputs can carry the prompt in file metadata (PNG text chunks, EXIF,
  XMP). Strip metadata before serving.
- Rate-limit and log extraction attempts; monitor rather than promise perfection.

## 6. Verify

Run the scanner over **client-facing** output only (server bundles legitimately
contain the template):

```bash
# 1. Positive control: confirm the scanner sees a fragment you plant on purpose
python3 scripts/scan_leaks.py --secrets server/skills --text "$(head -c 400 server/skills/product-stylist.txt)"

# 2. Build output that ships to browsers
python3 scripts/scan_leaks.py --secrets server/skills .next/static        # Next.js
python3 scripts/scan_leaks.py --secrets server/skills dist                # Vite/SPA

# 3. Rendered pages and API responses (run the app first)
python3 scripts/scan_leaks.py --secrets server/skills --url http://localhost:PORT/stylist

# 4. Everything the browser received during a real session
#    DevTools > Network > Export HAR (include a generation, a history load, an error)
python3 scripts/scan_leaks.py --secrets server/skills session.har
```

Exit code 1 means a leak; each hit names the file (or HAR entry), how much of which
secret matched, and a snippet. The scanner finds verbatim copies, including escaped and
partial ones; it cannot see a paraphrase. A field that a model writes from the template
(a tool argument, a "revised prompt", a node parameter) can leak the recipe in other
words, so make sure no such field reaches the browser rather than relying on the scan. Also check by hand in the browser: Application tab
(localStorage, IndexedDB, cookies), the console, the rendered DOM, and a forced error
(invalid input, provider failure). Repeat after every change to the feature: leaks
come back through new fields, new debug output and new error paths.

## 7. Report honestly

When you finish, state: which secrets were moved, which surfaces were checked and how
(scanner targets, HAR, manual), the positive-control result, and what remains
possible (output-based extraction, inference from results). Do not claim a prompt is
"impossible to copy".

## Anti-patterns

- Template in a `NEXT_PUBLIC_` / `VITE_` / `PUBLIC_` env var or a JSON file imported by client code.
- Template passed as a prop from a server component, loader or `getServerSideProps`.
- `{ result, debug: { prompt } }` or the raw provider response returned to the client.
- Showing a provider error after string-replacing the prompt out of it (truncated quotes survive).
- A tool with a `prompt` argument shown in the chat, "protected" by an echo filter (paraphrases survive).
- History rows, share links or "copy prompt" / "remix" buttons exposing the composed prompt.
- A quote, moderation or analytics call sent from the browser with the full prompt.
- The agent writing the composed prompt into a visible node or card parameter.
- Narrowing what users may ask for as a security measure.
