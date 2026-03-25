import type { PropsWithChildren, ReactNode } from "react";

interface PanelProps extends PropsWithChildren {
  title: string;
  copy?: string;
  actions?: ReactNode;
}

export function Panel({ title, copy, actions, children }: PanelProps) {
  return (
    <section className="panel">
      <header className="panel-header">
        <div>
          <h2 className="panel-title">{title}</h2>
          {copy ? <p className="panel-copy">{copy}</p> : null}
        </div>
        {actions}
      </header>
      {children}
    </section>
  );
}
