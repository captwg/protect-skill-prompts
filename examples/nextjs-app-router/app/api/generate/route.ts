import { callModel } from '@/lib-model'
import { compose, SKILL_ID } from '@/server/skills'

// Body: { skillId, choices: { style }, userRequest }. Never a prompt.
export async function POST(req: Request) {
  const body = await req.json().catch(() => null)
  if (body?.skillId !== SKILL_ID) return Response.json({ error: 'unknown_skill' }, { status: 404 })

  const prompt = compose(String(body.choices?.style), String(body.userRequest ?? ''))
  if (!prompt) return Response.json({ error: 'invalid_choice' }, { status: 400 })

  try {
    const out = await callModel(prompt)
    return Response.json({ result: out.text }) // only what the UI needs
  } catch (err) {
    console.error('generation failed', err) // provider errors may quote the prompt: server log only
    return Response.json({ error: 'generation_failed' }, { status: 502 })
  }
}
