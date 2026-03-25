import type { PropsWithChildren, ReactNode } from "react";

interface HeroProps extends PropsWithChildren {
  title: string;
  copy: string;
  badge: string;
  right?: ReactNode;
}

export function Hero({ title, copy, badge, right, children }: HeroProps) {
  return (
    <section className="hero">
      <div>
        <div className="hero-badge">{badge}</div>
        <h1 className="hero-title">{title}</h1>
        <p className="hero-copy">{copy}</p>
        {children}
      </div>
      <div className="hero-stack">{right}</div>
    </section>
  );
}
