# Governance

TVL (the Tuned Variables Language, see the [formal semantics](formalization/tvl-formal-semantics.md)) is a maintainer-led open-source project. Traigent Ltd. stewards it: Traigent maintainers make the decisions described here. There is no foundation, steering committee or voting body.

## Roles

- **Contributors** open issues and pull requests. Anyone may contribute, under the [Code of Conduct](CODE_OF_CONDUCT.md) and the sign-off (DCO) described in [CONTRIBUTING.md](CONTRIBUTING.md).
- **Maintainers** review and merge pull requests, run the [RFC process](formalization/README.md) (the written proposal process for language changes) and cut releases. They are listed in [MAINTAINERS.md](MAINTAINERS.md).

## How decisions are made

- **Ordinary changes** (bug fixes, documentation, tooling, examples) need review by a maintainer and a passing CI run. A maintainer merges.
- **Changes to the language** (grammar, schemas, the meaning of a construct, diagnostic codes, the promotion contract) go through the [RFC process](formalization/README.md). A maintainer accepts or rejects the RFC, and records the decision and the reason in the RFC's status. Discussion happens in the open, on the RFC's pull request.
- **Disagreement.** Maintainers aim for consensus in the open discussion. If it does not come, the Traigent maintainers decide and write down why. A contributor who disagrees may say so on the issue or pull request, and may use the licence to fork.

## Which source governs

For meaning, `formalization/tvl-formal-semantics.md` governs. For syntax and document shape, `spec/grammar/tvl.ebnf` and the JSON schemas in `spec/grammar/` govern. Accepted RFCs govern where the formal semantics is silent, and record the rationale. The Python reference implementation (`python/tvl`, `tvl_tools`) is reference behaviour, not normative. Docs, the book and the website are informative. Any disagreement between these sources is a defect to report and fix, not a choice for the reader.

## Compatibility

A change to a released language version must be a conservative extension: a document that was valid and meant something under 1.2 keeps its meaning. A change that cannot be conservative needs an RFC that states the break and a new language version.

## Becoming a maintainer

Maintainers invite contributors with a sustained record of good reviews and changes. There is no application process. Invitations and removals are recorded in [MAINTAINERS.md](MAINTAINERS.md).

## Changing this document

Governance changes are proposed by pull request and decided by the maintainers.
