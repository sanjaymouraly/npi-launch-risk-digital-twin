import React from 'react'

function inline(text: string, keyPrefix: string): React.ReactNode[] {
  const tokens = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return tokens.map((token, index) => {
    if (token.startsWith('**') && token.endsWith('**')) {
      return <strong key={`${keyPrefix}-${index}`}>{token.slice(2, -2)}</strong>
    }
    if (token.startsWith('`') && token.endsWith('`')) {
      return <code key={`${keyPrefix}-${index}`}>{token.slice(1, -1)}</code>
    }
    return <React.Fragment key={`${keyPrefix}-${index}`}>{token}</React.Fragment>
  })
}

export default function Markdown({ text }: { text: string }) {
  const lines = text.split('\n')
  const blocks: React.ReactNode[] = []
  let list: string[] = []
  let listType: 'ul' | 'ol' = 'ul'

  const flush = () => {
    if (!list.length) return
    const items = list.map((item, index) => <li key={index}>{inline(item, `li-${blocks.length}-${index}`)}</li>)
    blocks.push(listType === 'ul' ? <ul key={`ul-${blocks.length}`}>{items}</ul> : <ol key={`ol-${blocks.length}`}>{items}</ol>)
    list = []
  }

  lines.forEach((raw, index) => {
    const line = raw.trimEnd()
    if (!line.trim()) {
      flush()
      return
    }
    if (/^#{1,4}\s/.test(line)) {
      flush()
      const level = line.match(/^#+/)?.[0].length || 1
      const content = line.replace(/^#+\s*/, '')
      if (level <= 2) blocks.push(<h3 key={index}>{inline(content, `h-${index}`)}</h3>)
      else blocks.push(<h4 key={index}>{inline(content, `h-${index}`)}</h4>)
      return
    }
    if (/^>\s?/.test(line)) {
      flush()
      blocks.push(<blockquote key={index}>{inline(line.replace(/^>\s?/, ''), `q-${index}`)}</blockquote>)
      return
    }
    if (/^[-*]\s+/.test(line)) {
      if (listType !== 'ul') flush()
      listType = 'ul'
      list.push(line.replace(/^[-*]\s+/, ''))
      return
    }
    if (/^\d+\.\s+/.test(line)) {
      if (listType !== 'ol') flush()
      listType = 'ol'
      list.push(line.replace(/^\d+\.\s+/, ''))
      return
    }
    if (/^_Sources:/.test(line) || /^_/.test(line)) {
      flush()
      blocks.push(
        <p className="md-note" key={index}>
          {inline(line.replace(/^_|_$/g, ''), `n-${index}`)}
        </p>,
      )
      return
    }
    if (/^\|/.test(line)) {
      flush()
      blocks.push(
        <p className="md-table-line" key={index}>
          {line}
        </p>,
      )
      return
    }
    flush()
    blocks.push(<p key={index}>{inline(line, `p-${index}`)}</p>)
  })
  flush()
  return <div className="markdown">{blocks}</div>
}
