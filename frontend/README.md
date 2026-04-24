# Receptra Frontend

React 19 + Vite 6 + TypeScript + Tailwind v4. Browser sidebar for the Receptra Hebrew voice co-pilot.

## Quickstart

```bash
cd frontend
npm install
npm run dev             # http://localhost:5173
```

Dev server proxies `/api/*` → backend :8080 and `/ws/*` → backend WebSocket.

## Scripts

| Script                 | Purpose                       |
| ---------------------- | ----------------------------- |
| `npm run dev`          | Vite dev server with HMR      |
| `npm run build`        | Production bundle in `dist/`  |
| `npm run preview`      | Preview the production bundle |
| `npm run lint`         | ESLint 9 (flat config)        |
| `npm run typecheck`    | `tsc --noEmit`                |
| `npm run format:check` | Prettier check (CI)           |
| `npm run format`       | Prettier write                |

## Phase scope

Phase 1 ships only an empty RTL page. The real Hebrew sidebar UX — mic capture, live transcript, suggestion cards, citation chips, `hebrew-tailwind-preset` install — lands in Phase 6.
