# DesignQA frontend

## Run locally

From this directory, use Node.js compatible with Vite 8.

```powershell
npm ci
npm run dev
npm run build
```

The development server proxies same-origin `/api` requests to FastAPI on `127.0.0.1:8000`. The production bundle expects the same API paths on its origin. See [web architecture](../docs/WEB_ARCHITECTURE.md) for the endpoint overview and [API types](src/api.ts) for the response shapes and stage identifiers expected by the frontend.

## Request formats

- `POST /api/analyze` takes `mode` and an array of numeric `breakpoints`. Figma mode sends `figma_url`, `live_url`, optional `figma_token`, and a `hide_selectors` array. Demo mode sends `demo_variant` as `baseline` or `buggy`.
- `POST /api/analyze/{job_id}/frames` takes `frames`, an array of breakpoint and frame_id pairs.
- `POST /api/analyze/{job_id}/mapping` takes `mappings`, an array of node_id, breakpoint, and selector values. A null selector means the layer was skipped.
- Similarities are fractions from 0 to 1. Image values are browser-accessible artifact URLs. An event in the stage history records a completed stage. The current stage is supplied separately.

See [web test results](../docs/WEB_TEST_RESULTS.md) for API and browser verification.
