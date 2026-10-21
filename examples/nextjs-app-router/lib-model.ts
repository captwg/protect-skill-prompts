// Stand-in for a real model provider so the example runs without an API key.
// Replace with your provider SDK call; keep it in server code.
export async function callModel(prompt: string): Promise<{ text: string }> {
  await new Promise(r => setTimeout(r, 50))
  return { text: `Generated an image for a ${prompt.length}-character request.` }
}
