/** What a reader sees for a value the server did not send. Never "unknown", never an invented placeholder. */
export const NOT_AVAILABLE = 'not available'

/** A text field as shown: blank text reads as not available. */
export function shownText(value: string): string {
  const trimmed = value.trim()
  return trimmed === '' ? NOT_AVAILABLE : trimmed
}

/** Details as plain paragraphs: split on blank lines. The server has already stripped the markers. */
export function detailParagraphs(details: string): string[] {
  return details
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter((paragraph) => paragraph !== '')
}
