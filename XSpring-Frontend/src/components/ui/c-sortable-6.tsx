import * as React from "react"

export type SortableItem = { id: string; [key: string]: unknown }

export function CSortable6({ items = [], className = "", renderItem }: {
  items?: SortableItem[]
  className?: string
  renderItem?: (item: SortableItem, index: number) => React.ReactNode
}) {
  return (
    <div className={className}>
      {items.map((item, index) => renderItem ? renderItem(item, index) : <div key={item.id}>{item.id}</div>)}
    </div>
  )
}

export default CSortable6
