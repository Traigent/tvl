# TVL Website Deployment

`tvl-lang.org` currently serves static assets from S3 behind CloudFront. The React app in
`website/` can publish into that same stack.

## What Deploys

- Build output: `website/dist/public/`
- Canonical content is synced from `tvl/**` during the build
- The deploy workflow invalidates CloudFront after each publish

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

This site is an SPA with client-side routes such as `/specification`, `/examples`, and `/book`.
The build now exports route-specific `index.html` files plus a `404.html`, but the distribution
should still be configured to treat SPA routes correctly.

Minimum settings:

- Default root object: `index.html`
- S3 origin serves the contents of the site bucket
- CloudFront invalidations are allowed for the deploy role

Recommended SPA fallback:

- If the distribution uses an S3 REST origin:
  configure custom error responses for `403` and `404` to return `/index.html` with `200`
- If the distribution uses an S3 website endpoint:
  configure the error document to `404.html`

Without one of those fallbacks, direct visits to unknown client-side routes can still fail even
though the build exports the common route entry points.

## Trigger

The workflow should deploy on pushes to the default branch when changes touch:

- `website/**`
- `spec/**`
- `docs/**`
- `tvl_book/**`
- `python/**`
- `tvl_tools/**`

It also supports manual dispatch.
