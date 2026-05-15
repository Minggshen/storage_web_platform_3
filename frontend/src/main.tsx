import "./index.css";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ErrorBoundary
        fallback={
          <div
            role="alert"
            className="flex min-h-screen items-center justify-center bg-background"
          >
            <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-8 text-center">
              <h1 className="mb-3 text-xl font-bold text-foreground">
                系统异常
              </h1>
              <p className="mb-6 text-sm text-muted-foreground">
                请刷新页面重试，如问题持续存在请联系技术支持。
              </p>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="rounded-xl bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                刷新页面
              </button>
            </div>
          </div>
        }
      >
        <App />
      </ErrorBoundary>
    </BrowserRouter>
  </React.StrictMode>,
);
