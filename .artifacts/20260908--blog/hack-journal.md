# Hack journal

This journal records the low-risk addition of a Betwixt release announcement to the blog.


## Change

Added `docs/source/posts/2026-09-08--introducing-betwixt-a-home-for-boundary-model-mappings.md`, announcing the first
full-featured `betwixt-data` release and linking to its PyPI package, repository, and documentation.

The post uses the current public API documented by Betwixt, including `field_refs`, directional mappings, expansions,
runtime context, optional adapters, partial translations, nested mappings, and the guided demo. Added a nested checkout
example and a partial product update example in response to requested coverage beyond the basic field mapping. The
account example now uses actual SQLAlchemy ORM and Pydantic declarations, including storage and wire aliases. Reoriented
the account mapping so Pydantic is consistently the left side and SQLAlchemy is the right side. Documented class-wide
direction-specific controls for disabling implicit same-name mappings, with a plain-language explanation of when to use
the directional controls. Expanded the declaration-order explanation to describe top-to-bottom execution and
last-write-wins behavior.
Updated the demo command to include the `demo`, `pydantic`, and `sqlalchemy` extras so readers can run all examples from
the post.


## Verification

The Markdown formatter completed successfully after adding the examples. `make docs/build` completed successfully.
MkDocs
reported one existing warning in `posts/2025-11-25--uefi-arch-throwback-2012.md` for the unresolved link
`bbs.archlinux.org`; it is unrelated to this post.
