import type { PropsWithChildren, ReactNode } from "react";

interface HeroProps extends PropsWithChildren {
  title: string;
  copy?: string;
  badge?: string;
  right?: ReactNode;
}

export function Hero({ title, copy, badge, right, children }: HeroProps) {
  return (
    <section className="hero">
      <div>
        {badge ? <div className="pill" style={{ marginBottom: 6, fontSize: 11 }}>{badge}</div> : null}
        <h1 className="hero-title">{title}</h1>
        {copy ? <p style={{ margin: "4px 0 0", color: "var(--muted)", fontSize: 13 }}>{copy}</p> : null}
        {children}
      </div>
      <div className="hero-stack">{right}</div>
    </section>
  );
}
