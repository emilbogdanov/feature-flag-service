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

In the compose stack the dashboard is built into the proxy's image (`Dockerfile` here, built from
the repository root) and nginx serves it on http://localhost:8080/dashboard/. Its assets are named
by content hash and cached for a year; `index.html` is checked on every load. Pages get a content
security policy that allows nothing from other origins.

## What it does

- Projects, their environments and each environment's ruleset version.
- Flags with a switch for each environment. Turning one off never checks the version, so it always
  works as a kill switch; turning one on only goes ahead if the flag is still what you saw.
- New flags of any kind, with their variants, and edits to their name, description and variants.
- Each environment's targeting: ordered rules on attributes and user lists, a variant or a
  percentage split for each rule and for everyone else. Saving names the version the edit started
  from, so a change made meanwhile is shown instead of overwritten.
- API keys: issuing admin and SDK keys, with the secret shown once, and revoking them.
- The audit log, for every project or one, a page at a time.

## Signing in

The dashboard asks for an admin key, the same kind of key the API takes, and checks it by loading
the project list. The first one comes from `flagstaff-server create-admin-key`. The key is kept in
the tab's session storage, so a reload keeps you signed in and closing the tab signs you out. When
the API stops accepting the key, because someone revoked it, the next request signs you out.

## API types

`src/api/schema.ts` is generated, not written by hand. After a change to the API:

```
npm run generate:api
```

The script asks the backend for its schema with `uv run flagstaff-server openapi`, so it needs
[uv](https://docs.astral.sh/uv/). The file is committed so the dashboard builds without Python. CI
generates it again and fails when the committed file no longer matches the API.

## End-to-end tests

`e2e/` holds Playwright tests that use the dashboard in the compose stack the way a person would,
then check through the API what it did: that a flag targeted in the editor is served as targeted,
that the kill switch works, that an SDK key issued in the dashboard reads rules until it is revoked
there. Each test makes a project of its own, so they don't depend on what the stack already holds.

```
docker compose up --build --wait
npx playwright install chromium
FLAGSTAFF_ADMIN_KEY=$(docker compose exec -T api-1 flagstaff-server create-admin-key --name e2e) npm run e2e
```

`FLAGSTAFF_STACK_URL` points them at a stack somewhere other than `http://localhost:8080`.

## Checks

| Command                |                                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------ |
| `npm run lint`         | ESLint with typescript-eslint's strict, type-checked rules and the React hooks rules |
| `npm run format:check` | Prettier                                                                             |
| `npm run typecheck`    | `tsc --build` over the app, both kinds of tests, the configs and the scripts         |
| `npm test`             | Vitest and Testing Library in jsdom                                                  |
| `npm run build`        | type check, then the production bundle in `dist/`                                    |
| `npm run e2e`          | Playwright against the compose stack, as above                                       |
