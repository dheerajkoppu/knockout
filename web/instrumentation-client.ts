import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || process.env.NODE_ENV,
    integrations: [
      Sentry.browserTracingIntegration(),
      Sentry.replayIntegration({ maskAllText: false, maskAllInputs: false, blockAllMedia: false }),
    ],
    tracesSampleRate: 1.0,
    // Trace headers make the API's CORS preflight stricter, so they go only where the API allows them.
    tracePropagationTargets: process.env.NEXT_PUBLIC_SENTRY_TRACE_API === "true" ? [apiUrl] : [],
    replaysSessionSampleRate: 1.0,
    replaysOnErrorSampleRate: 1.0,
  });
}

export const onRouterTransitionStart = dsn ? Sentry.captureRouterTransitionStart : undefined;
