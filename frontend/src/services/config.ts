/** Single switch between mock and real adapters (create.md sec.37/43).
 * Defaults to mock: the real backend's /api/generate is gated behind a
 * real Monitor (which isn't configured in this standalone build - see
 * create.md sec.1), and has no HTML-preview/draft-save/history/reference
 * endpoints yet at all, so mock is what actually lets Generate/History/
 * Reference be exercised end-to-end today. Set VITE_USE_MOCK_API=false
 * once the backend gaps noted in services/api/*.ts are filled in. */
export const USE_MOCK_API = !import.meta.env.PROD && import.meta.env.VITE_USE_MOCK_API !== "false";

/** Development/Test ONLY, and only when explicitly set (VITE_DEV_GENERATE=true) together with
 * VITE_USE_MOCK_API=false: the Generate button posts to the backend's POST /api/dev/generate
 * instead of the production POST /api/generate. Both run the SAME real Generator; the only
 * difference is that the dev route skips the Monitor READY gate (backend must be started with
 * GENERATOR_DEV_MODE=true, otherwise that route does not exist and Generate fails visibly with
 * the backend's real 404 - there is no silent fallback to /api/generate or to mock data).
 * Default (unset) = production route, Monitor-gated. */
export const USE_DEV_GENERATE = !import.meta.env.PROD && import.meta.env.VITE_DEV_GENERATE === "true";
export const GENERATE_PATH = USE_DEV_GENERATE ? "/api/dev/generate" : "/api/generate";
