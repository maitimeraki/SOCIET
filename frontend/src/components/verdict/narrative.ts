export interface NarrativeSection {
  heading: string
  body: string
}

/**
 * Split the synthesis markdown into `## ` sections. No markdown library — the
 * narrative is only ever headings plus paragraphs, so a line splitter covers it
 * (§8.4). Text before the first heading becomes a heading-less preamble section.
 */
export function splitSections(markdown: string): NarrativeSection[] {
  const sections: NarrativeSection[] = []
  let heading = ''
  let body: string[] = []
  const flush = () => {
    const text = body.join('\n').trim()
    if (heading || text) sections.push({ heading, body: text })
  }
  for (const line of markdown.split('\n')) {
    if (line.startsWith('## ')) {
      flush()
      heading = line.slice(3).trim()
      body = []
    } else {
      body.push(line)
    }
  }
  flush()
  return sections
}
