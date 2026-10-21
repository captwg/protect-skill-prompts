# Next.js App Router example

A one-page "product stylist" whose prompt template never reaches the browser.

| File | Role |
|---|---|
| `server/skills.ts` | The template, behind `import 'server-only'`. `compose()` joins template, choice and the user's words. |
| `app/api/generate/route.ts` | Takes `{ skillId, choices, userRequest }`, composes, calls the model, returns only the result. Provider errors stay in the server log. |
| `app/stylist/page.tsx` | Passes the skill id and style list to the client component, never the template. |
| `components/StylistForm.tsx` | Sends choices and the user's own words. |

```bash
pnpm install   # or npm install
pnpm verify    # builds, starts on port 4319, scans the bundle, page and API responses
```

Try breaking it to see the scanner catch each classic mistake:

1. Pass the template as a prop: `<StylistForm template={TEMPLATE} … />` (leaks through the page payload even if never rendered).
2. Remove `import 'server-only'` and import `compose` in `StylistForm.tsx` (leaks into the JS bundle).
3. Return `{ result, debug: { prompt } }` from the route (leaks through the API response).
