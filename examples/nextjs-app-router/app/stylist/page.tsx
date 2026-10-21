import StylistForm from '@/components/StylistForm'
import { SKILL_ID, STYLES } from '@/server/skills'

// Pass ids and display data to the client component. Every prop is serialized into the page.
export default function Page() {
  return <StylistForm skillId={SKILL_ID} styles={STYLES} />
}
