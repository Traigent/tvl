# TVL Website Deployment

`tvl-lang.org` currently serves static assets from S3 behind CloudFront. The React app in
`website/` can publish into that same stack.

## What Deploys

- Build output: `website/dist/public/`
- Canonical content is synced from `tvl/**` during the build
- The deploy workflow invalidates CloudFront after each publish
- `website/server/index.ts` (the Express app, including its rate limiter) is
  **not** part of this path — it is a local-dev/preview-only entry point
  (`pnpm start` / `pnpm preview`). Any app-level rate limiting or abuse
  protection for the live `tvl-lang.org` site must be configured at the
  CloudFront/WAF layer, not in this server.

## Required GitHub Configuration

Set these before enabling the workflow:

- Actions secret: `AWS_ROLE_TO_ASSUME`
- Actions variable: `AWS_REGION`
- Actions variable: `TVL_WEBSITE_S3_BUCKET`
- Actions variable: `TVL_WEBSITE_CLOUDFRONT_DISTRIBUTION_ID`

Recommended:

- `AWS_REGION`: the region where the S3 bucket and distribution are managed
- `TVL_WEBSITE_S3_BUCKET`: the bucket serving `www.tvl-lang.org`
- `TVL_WEBSITE_CLOUDFRONT_DISTRIBUTION_ID`: the distribution in front of that bucket

The workflow assumes AWS access through GitHub OIDC via `AWS_ROLE_TO_ASSUME`.

## One-Time CloudFront / S3 Settings

This site is an SPA, but every client-side route (`/`, `/specification`, the `/specification/*`
reference pages, `/examples`, `/github`, `/book`) is exported at build time as its own
`index.html`, so no SPA fallback is needed. Unknown URLs must return a real `404`:
`client/public/404.html` is a standalone page that does not depend on the app bundle.

Minimum settings:

- Default root object: `index.html`
- S3 origin serves the contents of the site bucket
- CloudFront invalidations are allowed for the deploy role

Error handling (required, so unknown URLs are not served as soft 404s):

- If the distribution uses an S3 REST origin:
  configure custom error responses for `403` and `404` to return `/404.html` with response code
  `404`. Do **not** map them to `/index.html` with `200`: that makes every unknown URL look like a
  valid page to browsers, crawlers, and link checkers.
- If the distribution uses an S3 website endpoint:
  configure the error document to `404.html`

Verify after a deploy: `curl -s -o /dev/null -w '%{http_code}' https://tvl-lang.org/does-not-exist`
prints `404`, and `curl -s -o /dev/null -w '%{http_code}' https://tvl-lang.org/specification`
prints `200`.

The build also writes `sitemap.xml` from the list of indexable routes in
`scripts/prepare_static_deploy.mjs`; add a new public route there (and to its static route list)
when you add a page.

## Trigger

The workflow should deploy on pushes to the default branch when changes touch:

- `website/**`
- `spec/**`
- `docs/**`
- `tvl_book/**`
- `python/**`
- `tvl_tools/**`

It also supports manual dispatch.
