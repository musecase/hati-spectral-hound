# HATI judge site

This is the public Build Week experience for HATI — Spectral Hound. It uses the
OpenAI Sites vinext/Cloudflare production starter and contains no household media,
credentials, camera addresses, or live device controls.

## Run locally

Node 24 or newer is required.

```powershell
npm ci --ignore-scripts --no-audit --no-fund
npm run dev
```

## Verify

```powershell
npm run lint
npm test
```

`npm test` performs a production build and server-renders the page, then checks
the project title, evidence lab, controlled-evaluation label, video slot, honesty
section, Open Graph metadata, and public repository link.

The raccoon/coop hero is a labeled concept illustration generated for the social
preview. It is not presented as surveillance footage. The interactive cases are
reconstructions of deterministic sample fixtures in the parent repository.
