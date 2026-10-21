'use client'
import { useState } from 'react'

export default function StylistForm({ skillId, styles }: { skillId: string; styles: readonly string[] }) {
  const [style, setStyle] = useState(styles[0])
  const [userRequest, setUserRequest] = useState('')
  const [result, setResult] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const res = await fetch('/api/generate', {
      method: 'POST',
      body: JSON.stringify({ skillId, choices: { style }, userRequest }),
    })
    const data = await res.json()
    setResult(data.result ?? 'Something went wrong. Please try again.')
  }

  return (
    <form onSubmit={submit}>
      <select value={style} onChange={e => setStyle(e.target.value)}>
        {styles.map(s => <option key={s}>{s}</option>)}
      </select>
      <input
        placeholder="Anything you want changed, in your own words"
        value={userRequest}
        onChange={e => setUserRequest(e.target.value)}
      />
      <button>Generate</button>
      <p>{result}</p>
    </form>
  )
}
