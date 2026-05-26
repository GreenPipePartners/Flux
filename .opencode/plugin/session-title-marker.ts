import type { Plugin } from "@opencode-ai/plugin"

const TITLE_MARKER = /^\s*;;(.+?);;\s*/s

function titleFromMarker(text: string): { title: string; marker: string } | undefined {
  const match = text.match(TITLE_MARKER)
  const title = match?.[1]?.trim().replace(/\s+/g, " ")

  if (!match || !title) return undefined

  return { title, marker: match[0] }
}

export default (async ({ client }) => {
  return {
    "chat.message": async (input, output) => {
      const textPart = output.parts.find((part) => part.type === "text")
      if (!textPart || textPart.type !== "text") return

      const marker = titleFromMarker(textPart.text)
      if (!marker) return

      await client.session.update({
        path: { id: input.sessionID },
        body: { title: marker.title },
      })

      textPart.text = textPart.text.replace(marker.marker, "").trimStart()
    },
  }
}) satisfies Plugin
