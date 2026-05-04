// Regression fixture: mirrors the real-world pattern that caused
// languageId=typescript (instead of typescriptreact) to truncate symbol
// ranges at the first multi-line JSX expression.

import * as React from "react"

type SectionProps = { title: string; emphasised?: boolean }

function Section({ title, emphasised }: SectionProps) {
  return emphasised ? (
    <h1 style={{ color: "red" }}>{title}</h1>
  ) : (
    <h2 style={{ color: "gray" }}>{title}</h2>
  )
}

export function JsxComponent({ heading, items }: { heading: string; items: string[] }) {
  const renderHeader = (title: string) =>
    title.length > 10 ? (
      <Section title={title} emphasised />
    ) : (
      <Section title={title} />
    )

  // The truncation bug used to cut JsxComponent's range right around here,
  // hiding everything below from find_symbol. Keep this comment so the
  // regression test can assert the function body extends past it.
  const renderItem = (item: string, idx: number) => (
    <li key={idx} style={{ marginBottom: 4 }}>
      {item}
    </li>
  )

  return (
    <div>
      {renderHeader(heading)}
      <ul>{items.map(renderItem)}</ul>
    </div>
  )
}

export function trailingHelper(): string {
  return "this symbol is invisible to find_symbol when JsxComponent's range is truncated"
}
