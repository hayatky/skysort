import { jsx as _jsx } from "react/jsx-runtime";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter } from "react-router-dom";
export function AppProviders({ children }) {
    const [queryClient] = useState(() => new QueryClient({
        defaultOptions: {
            queries: {
                staleTime: 1_000,
                refetchOnWindowFocus: false,
            },
        },
    }));
    return (_jsx(QueryClientProvider, { client: queryClient, children: _jsx(BrowserRouter, { children: children }) }));
}
