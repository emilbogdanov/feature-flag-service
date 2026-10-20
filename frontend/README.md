# Flagstaff dashboard

The web dashboard for the [Flagstaff](../README.md) API: React and TypeScript, built with Vite. It
works with an admin key and reaches the API through a client typed from the API's own OpenAPI
document, so a renamed field or endpoint fails the type check instead of a page.

## Running it

Needs Node 24 and the API, for example the compose stack on `localhost:8080`:

```
npm ci
npm run dev
```

The dashboard opens on http://localhost:5173/dashboard/. It lives under `/dashboard/` because the
API owns the paths at the root. Vite forwards the API's paths to `FLAGSTAFF_API_URL` (default
`http://localhost:8080`), so the browser sees one origin, as it does behind nginx.

## API types

`src/api/schema.ts` is generated, not written by hand. After a change to the API:

```
npm run generate:api
```

The script asks the backend for its schema with `uv run flagstaff-server openapi`, so it needs
[uv](https://docs.astral.sh/uv/). The file is committed so the dashboard builds without Python. CI
generates it again and fails when the committed file no longer matches the API.

## Checks

| Command                |                                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------ |
| `npm run lint`         | ESLint with typescript-eslint's strict, type-checked rules and the React hooks rules |
| `npm run format:check` | Prettier                                                                             |
| `npm run typecheck`    | `tsc --build` over the app, the tests, the Vite config and the scripts               |
| `npm test`             | Vitest and Testing Library in jsdom                                                  |
| `npm run build`        | type check, then the production bundle in `dist/`                                    |
