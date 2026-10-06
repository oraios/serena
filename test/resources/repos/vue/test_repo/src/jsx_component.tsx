// Regression fixture for Vue TS companion languageId (#1436 class of bug).

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
  return "this symbol is invisible when JsxComponent's range is truncated"
}
