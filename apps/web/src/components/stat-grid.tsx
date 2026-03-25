export interface StatItem {
  label: string;
  value: string | number;
}

export function StatGrid({ items }: { items: StatItem[] }) {
  return (
    <dl className="stats">
      {items.map((item) => (
        <div key={item.label} className="stat-card">
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
