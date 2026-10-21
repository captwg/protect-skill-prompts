import 'server-only' // a client component that imports this file fails the build

// The secret. It never leaves the server: not in props, responses, history or errors.
const TEMPLATE = `You are a senior product photographer for premium e-commerce catalogs. Light the product with a soft key from the upper left, a warm rim light behind it, and a seamless gradient backdrop that fades from charcoal to slate. Keep reflections crisp, keep the label fully legible, and never crop the logo. Style: {style}.`

export const SKILL_ID = 'product-stylist'
export const STYLES = ['studio', 'outdoor', 'flatlay'] as const

/** Compose late: only here, only in memory, right before the provider call. */
export function compose(style: string, userRequest: string): string | null {
  if (!(STYLES as readonly string[]).includes(style)) return null
  return (
    TEMPLATE.replace('{style}', style) +
    '\n\nUser request (takes priority over the defaults above): ' +
    (userRequest.slice(0, 2000) || 'none')
  )
}
