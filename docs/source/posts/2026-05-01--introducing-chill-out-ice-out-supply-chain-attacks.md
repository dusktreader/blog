---
date: 2026-05-01
authors:
- the.dusktreader
comments: true
tags:
- Python
- PyPI
- npm
- CLI
- GitHub
- CI
categories:
- dev-tools
---

# Introducing chill-out: ice out supply-chain attacks

!!! tip "TLDR"
    Every new dependency release is an attack window. `chill-out` audits your lockfile, blocks anything too fresh to
    trust, and fixes violations automatically. It works for Python and npm, and takes thirty seconds to wire into CI.

Your lockfile has a freshness problem you might not be thinking about. A new release of any package you depend on,
direct or transitive, is a window of time when a supply chain attack could reach your production environment before
anyone notices. `chill-out` closes that window by refusing any locked version that hasn't cleared a configurable
cooldown period.

<!-- more -->

## The threat model

Supply chain attacks almost always arrive the same way: a maintainer's token gets stolen, or a package name gets
squatted. Once compromised, a malicious release appears on PyPI or npm as something that looks like a routine version
bump. Automated dependency update tools (Dependabot, Renovate) see the new version, open a PR, and if your CI doesn't
object, the attack is one merge away from production.

The community is actually pretty good at catching these. Malicious packages rarely survive two weeks of public scrutiny
without someone noticing. The problem is that your CI probably merges dependency updates faster than that window closes.

**Cooldown** is the practice of refusing any version that has been public for less than some grace period. If your
cooldown window is 14 days and you run a check before every deploy, a malicious release has to survive 14 days of
public scrutiny before it can reach production. That's usually enough.

GitHub's Dependabot supports cooldown windows natively, but only as a filter on the versions it *proposes*. It never
audits what is already in your lockfile. If a dependency sneaks in through a manual edit, a Renovate merge, or a
`uv lock` run, Dependabot's cooldown is completely blind to it. `chill-out` audits the lockfile directly, on demand,
regardless of how those versions got there.


## Why the lockfile specifically

Most supply chain tooling audits your declared dependencies: the `requests` in your `pyproject.toml`, the `axios` in
your `package.json`. That's the wrong place to look.

What actually runs in your environment is what's in your lockfile. A dependency you declared is only a real risk once
it resolves to a specific version in `uv.lock` or `package-lock.json`. Transitive dependencies you never declared
directly are in that lockfile too, and they run in your environment just the same. A compromised `cryptography` release
pulled in transitively through `paramiko` is just as dangerous as one you added yourself.

`chill-out` reads the lockfile end-to-end: principals and transitives alike. It scans every package that will actually
be installed. There is no "direct deps only" mode because that would be lying about the threat surface.


## Getting started

Just install the package:

```shell-ps1
uv tool install chill-out
```

Then, in any Python or npm project:

```shell-ps1
chill-out check
```

`chill-out` auto-detects the ecosystem from the files it finds in the project root and loads whatever configuration
applies. With no config file, it uses sensible defaults: 30 days for major releases, 10 for minor, 7 for patch.

A clean project looks like this:

```
No cooldown violations across 47 pypi package(s).
```

A project with a fresh transitive looks like this:

```
2 cooldown violation(s) in 47 pypi package(s):
┌──────────────────────────────────────────────────────┬───────────┬─────────────────────────────────────────────┐
│ Package                                              │ Limit     │ Strategy                                    │
├──────────────────────────────────────────────────────┼───────────┼─────────────────────────────────────────────┤
│ httpx = 0.28.0 (age 3d > 10d)                        │ minor 10d │ httpx -> 0.27.2 (45d old)                   │
│ httpx = 0.28.0                                       │ minor 10d │ httpx -> 0.27.2 (45d old)                   │
│ └─ anyio = 4.7.0 (age 3d > 10d)                      │ minor 10d │ anyio -> 4.6.2 (60d old)                    │
└──────────────────────────────────────────────────────┴───────────┴─────────────────────────────────────────────┘
```

Reading the output: `httpx 0.28.0` is a minor release that shipped 3 days ago, but your minor threshold is 10 days,
so it's blocked. The second row shows that `httpx 0.28.0` also pulled in `anyio 4.7.0` as a transitive, which is
equally fresh. The `Strategy` column tells you the safe rollback target for each: `httpx 0.27.2`, which has been
public for 45 days, and `anyio 4.6.2` at 60 days. You don't have to dig through release histories yourself.


## Fixing violations

```shell
chill-out fix
```

`fix` rewrites your project manifest (`pyproject.toml` for Python, `package.json` for npm) and re-resolves the
lockfile. For Python projects it runs `uv lock` after rewriting; for npm it runs `npm install`. After writing the fixes,
it re-runs the check automatically so you can see whether everything cleared.

For the transitive violation above, `chill-out` walks `httpx`'s release history to find the most recent version whose
declared dependency range admits the safe `anyio 4.6.2`. It then writes exact pins for both: one rolling back the
principal, one hoisting the transitive into a direct pin so the resolver can't drift back. The paired principal
rollback is always exact regardless of your configured `fix_style`, because a range there could let the resolver slip
right back into the conflict.

By default, pins are written exactly:

```
pkg==1.2.3
```

If you set `fix_style: compatible` in your config, ordinary direct pins get written as ranges instead:

```
pkg>=1.2.3,<2.0.0
```

Compatible is there if you'd rather let the resolver pick up future safe patch and minor updates automatically without
another fix pass.

With exact style in particular, those hard version pins accumulate in your manifest and need to come out once the
avoided release has aged past its cooldown window. `chill-out` handles this automatically: every exact pin it writes
is recorded in `.chill-out-state.json`, and the next `chill-out fix` run removes any pins whose avoided release has
since cleared its cooldown. You don't have to track or clean them up yourself.


## Configuration

The preferred place for `chill-out` configuration is your project manifest, which keeps everything in one file:

```toml
# pyproject.toml
[tool.chill-out]
fix_style = "compatible"

[tool.chill-out.cooldown]
major = 60
minor = 14
patch = 7
default = 7
```

For npm projects, add a top-level `"chill-out"` key to `package.json` instead. If you'd rather not touch your
manifest at all, a dedicated `.chill-out.yaml` at the project root works too:

```yaml
# .chill-out.yaml
cooldown:
  major: 60
  minor: 14
  patch: 7
  default: 7
fix_style: compatible
```

If you're already using Dependabot's cooldown feature in `.github/dependabot.yml`, `chill-out` reads those thresholds
automatically when no other config is present, so you may not need to configure anything at all.


## Wiring it into CI

The exit code is the contract: `0` for a clean lockfile, `2` for at least one violation. That's all you need for a
gate:

```yaml
# .github/workflows/cooldown.yml
- name: Check dependency cooldown
  run: |
    pip install chill-out
    chill-out check --fast
```

`--fast` skips the safe-version lookup, saving an extra registry round trip per violation. Use it in CI where you only
care about pass/fail; the violation is still reported, you just won't see the rollback suggestion.

For a fully worked GitHub Actions setup, including scheduled audit jobs that open PRs when managed pins have aged out,
the [GitHub Actions](https://dusktreader.github.io/chill-out/github-actions/) page has copy-pasteable recipes.


## Trying it out without installing

If you want to see the tool against a real lockfile before committing, the repo ships a demo you can run directly with
`uvx`:

```shell
uvx --from "chill-out[demo]" chill-out-demo
```

## How it fits with Dependabot and Renovate

`chill-out` isn't a replacement for automated dependency update tools. It's a gate that sits next to them.

Dependabot and Renovate are good at opening PRs when new versions are available. They are not good at waiting.
Dependabot's native cooldown support only filters which versions it *proposes* in new PRs; it never audits your
existing lockfile for packages that are already locked to something too fresh. On top of that, it only runs on the
schedule you give it, so a malicious release that lands two hours after Dependabot's weekly job sails right through
until next week. `chill-out` fills both gaps: it audits the full lockfile, and it runs whenever you tell it to.

The intended workflow: let your update bot open the PRs, let `chill-out` veto the ones that aren't safe yet, merge
what passes and let what fails sit in the queue. On most days, nothing needs human attention.


## The state file

Each pin `chill-out` writes is recorded in `.chill-out-state.json` with a full receipt: which release was avoided,
what type it was, when it was published, and what threshold applied. You can read the file at any point and know
exactly why a pin is there without re-running a check or consulting the registry. When all managed pins retire, the
file is deleted rather than left behind as an empty shell.

Commit it. Your team shares the same view of what is pinned and why, and CI sees the same state your local runs do.


## Wrapping up

I built `chill-out` because the risk I was most worried about wasn't the packages I explicitly added; it was the
transitives that came along for the ride. You install something new, the resolver pulls in a fresh transitive you've
never heard of, and nothing flags it. You're exposed and you don't know it. Getting cooldown coverage over the full
lockfile, not just direct deps, and actually pinning the safe versions when something violates it turned out to be
enough of a pain that I wanted a tool to just handle it.

The [documentation](https://dusktreader.github.io/chill-out/) has a full quickstart, a detailed case study walking
through ninety days of dependency churn with `chill-out` in the loop, and the complete CLI reference.

Give it a try and let me know how it goes in the comments!
