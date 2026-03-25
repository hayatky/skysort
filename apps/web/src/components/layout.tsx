import { PropsWithChildren } from "react";

import { Sidebar } from "./sidebar";

export function AppLayout({ children }: PropsWithChildren) {
  return (
    <div className="shell">
      <div className="shell-grid">
        <Sidebar />
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
