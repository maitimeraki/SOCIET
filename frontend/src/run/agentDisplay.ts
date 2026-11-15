/** What a reader sees for a value the server did not send. Never "unknown", never an invented placeholder. */
export const NOT_AVAILABLE = 'not available'

/** A text field as shown: blank text reads as not available. */
export function shownText(value: string): string {
  const trimmed = value.trim()
  return trimmed === '' ? NOT_AVAILABLE : trimmed
}

/** The server's placeholder for an entity type it does not know. Mapped here, once; never shown as typed. */
const TYPE_PLACEHOLDER = 'type unknown'

/** An entity type as shown: the server's placeholder reads as not available, like any missing value. */
export function shownType(value: string): string {
  return value.trim().toLowerCase() === TYPE_PLACEHOLDER ? NOT_AVAILABLE : shownText(value)
}

/** Details as plain paragraphs: split on blank lines. The server has already stripped the markers. */
export function detailParagraphs(details: string): string[] {
  return details
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter((paragraph) => paragraph !== '')
}
