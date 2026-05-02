---
date: 2026-05-01
authors:
- the.dusktreader
comments: true
tags:
- Python,Pydantic,database,API,Long-form
categories:
- dev-tools
---

# Betwixt: a data transformation layer design spec

!!! tip "TLDR"
    Your DB type and your API type are not the same shape. Stop
    trying to squish them together with awkward hooks, aliases,
    and non-local mapping functions. Betwixt your models lives
    a new, delcarative mapping layer.

Pick any non-trivial Python backend. There is a database type (an
ORM row, a `@dataclass`, an attrs class) and there is an API type
(a Pydantic model, an msgspec struct, whatever the framework
demands). They are not the same shape. They cannot be the same
shape: one is constrained by the storage schema, the other by
the wire contract. Mapping between them is real work.

<!-- more -->

The Python ecosystem has no library for this. Pydantic,
marshmallow, attrs, msgspec, cattrs, dataclasses: every one of
them assumes data flows between *one* in-memory type and *one*
wire format. Mapping between two distinct in-memory types is
treated as a problem you solve by reaching for one of those
libraries twice and gluing the results together with a
`from_row()` classmethod and a `to_row()` instance method, or by
collapsing both types into a single Pydantic model and burying
the asymmetry inside `model_validator` and `model_serializer`.
Both approaches work. Neither reads well at scale. Neither makes
the asymmetric pieces (a field that exists only on one side, a
transform that needs different logic in each direction, a
runtime dependency the mapping needs) visible at a glance.

Betwixt is a design for that missing library. It is a
peer-to-peer mapping layer that sits on top of any
structured-type library, names the relationship between two
types as a first-class object, and treats directionality as a
visible concern at every declaration site. It does mapping and
nothing else. The existing libraries keep doing what they do.

This document is the spec, organized as a worked example. A
single running scenario (a `User` type that exists once as a DB
row and once as an API response) carries you through the
taxonomy of constructs, the runtime model, the partial-update
story, and a comparison against Pydantic-alone for the same
problem. Two further case studies at the back stress the spec
against shapes the running example doesn't reach: runtime
context with asymmetric directions
([Payment](#payment-runtime-context-asymmetric-directions-multi-field-inputs)),
and nesting in all its container shapes
([Order](#order-nesting-in-all-its-shapes)).
The doc closes with the affirmative case for the design, the
known risks, and an honest "when not to use this."

A reading guide for the impatient:

- [Design principles](#design-principles): the two load-bearing
  commitments (peer-to-peer, directional vocabulary).
- [The scenario](#the-scenario) and [The two sides](#the-two-sides):
  the running example and the types it operates on.
- [Betwixt](#betwixt): the full taxonomy of mapping constructs.
  This is the longest chapter and the heart of the spec.
- [Using Betwixt](#using-betwixt) and [Partial / patch translations](#partial-patch-translations):
  what call sites look like.
- [Pydantic alone vs. Pydantic + Betwixt](#pydantic-alone-vs-pydantic-betwixt):
  the side-by-side comparison.
- [Case studies](#case-studies): three larger examples that
  exercise the full taxonomy.
- [The case for Betwixt](#the-case-for-betwixt), [Risks](#risks),
  [Future validation](#future-validation),
  [When not to use Betwixt](#when-not-to-use-betwixt),
  [Conclusion](#conclusion): the closing arc.


## Design principles

Betwixt rests on two principles. Both are load-bearing.

### 1. Peer-to-peer, not source-to-target

A *betwixt* describes a **relationship between two structured types**, not
a one-way pipeline. Neither side is privileged. Mappings are declared
as symmetric facts ("`UserRow.email_address` corresponds to
`UserResponse.email`") whenever they are naturally invertible. When they
are not, the two directions are declared independently and explicitly.

This matters because:

- Reversibility is the exception, not the rule, for non-trivial transforms.
- Pretending one direction is "primary" leads to the asymmetry that makes
  Pydantic's `model_validator`-and-aliases-everywhere style feel grafted on.
- Forcing the user to spell out both directions when they differ makes
  hidden assumptions visible in code review.

The vocabulary follows from this. The two sides are **`left`** and
**`right`**; motion between them is **`leftward`** or **`rightward`**.
"Forward" and "reverse" are deliberately absent: they only have meaning
if one side is privileged as the source, which this model rejects.

### 2. The mapping layer, nothing else

Betwixt does **one** thing: it translates instances of one structured type
into instances of another. It does not validate. It does not serialize.
It does not parse JSON. It does not generate JSON Schema. It does not
integrate with FastAPI.

Each side keeps its own validation, serialization, and ecosystem
machinery. If the right side is a Pydantic model, you get all of
Pydantic's validation, JSON Schema generation, OpenAPI integration, and
error formatting for free -- because the right side *is* a Pydantic
model and Pydantic owns those concerns. Betwixt's only job is the
translation step in between.

This is a deliberate constraint. Validation and serialization are vast
problem spaces; competing on them would require Betwixt to reinvent what
Pydantic and others already do well, and the result would be a worse
version of an existing solution. The leverage is in the layer none of
those libraries provide: a first-class, declarative spec of how two
types relate.

The practical shape of this is a three-step flow at every translation
boundary:

```python
response = UserResponse.model_validate(api_json)   # Pydantic owns validation
row      = UserBetwixt.leftward(response)            # Betwixt owns translation
db_dict  = dataclasses.asdict(row)                 # stdlib owns serialization
```

Each tool does what it does best. Betwixt handles *one* part: data translation.

----

## The scenario

We have two structured types representing the same logical entity at
different boundaries:

- `UserRow`: how a user is stored in the database. A plain stdlib
  `@dataclass`. No validation needed at this boundary -- the database
  schema is the source of truth, and the ORM (or whatever sits between
  the database and Python) hands back already-typed values.
- `UserResponse`: how a user is returned from a public API endpoint. A
  Pydantic `BaseModel`. Validation matters here because the API
  contract is what untrusted clients consume and produce.

This pairing -- plain dataclass on the persistence side, Pydantic model
on the boundary side -- is the most common real-world case for a
mapping library. The dataclass and the Pydantic model are both
completely standard; neither has any Betwixt-specific decoration. Betwixt
attaches at the seam between them, not to the types themselves.

Differences between the two:

| Concern              | UserRow                          | UserResponse                          |
|----------------------|----------------------------------|---------------------------------------|
| Identity             | `id: int` (DB primary key)       | `id: str` (public slug)               |
| Name                 | `first_name`, `last_name`        | `full_name` (combined)                |
| Email                | `email_address: str`             | `email: str` (renamed)                |
| Timestamps           | `created_at: pendulum.DateTime`  | `created_at: pendulum.DateTime`       |
| Internal-only        | `password_hash`, `internal_note` | (absent)                              |
| Response-only        | (absent)                         | `is_recent: bool` (derived)           |
| Tags                 | `tags: list[str]`                | `tags: list[str]` (1:1)               |


## The two sides

Each side is whatever it would be without Betwixt. The DB-side type is a
plain stdlib dataclass; the API-side type is a plain Pydantic model.
Betwixt does not own either declaration.

```python
from dataclasses import dataclass
from pydantic import BaseModel
import pendulum

@dataclass
class UserRow:
    id: int
    first_name: str
    last_name: str
    email_address: str
    password_hash: str
    internal_note: str
    tags: list[str]
    created_at: pendulum.DateTime


class UserResponse(BaseModel):
    id: str
    full_name: str
    email: str
    tags: list[str]
    created_at: pendulum.DateTime
    is_recent: bool
```

Notice what's missing: no aliases on the Pydantic model, no `@validator`
methods, no `model_config = ConfigDict(populate_by_name=True)`, no
`Field(serialization_alias=...)`. The Pydantic model is exactly as
clean as it would be if `UserRow` did not exist. That asymmetry --
between how the DB stores a user and how the API exposes one -- lives
in the Betwixt model, not smuggled into either model.

Symmetric statement for the dataclass: `UserRow` is a plain dataclass.
No `field(metadata=...)` carrying mapping hints, no helper classmethods,
no `__init_subclass__` shenanigans. The DB layer's representation
stands on its own and would survive deletion of the API layer entirely.

### Adapters

The two sides above use different type-modeling libraries: stdlib
`@dataclass` on the left, Pydantic `BaseModel` on the right. Betwixt
treats both through the same internal interface: an **adapter**.

An adapter is a small `Protocol` with three responsibilities:

1. **List the side's fields** -- given the side's class, return the
   set of field names and their type annotations.
2. **Get a field by name** -- given an instance and a field name,
   return that field's value.
3. **Instantiate from a dict** -- given the side's class and a dict
   of field-name to value, return a constructed instance.

That is the entire contract. Anything Betwixt needs to do to a side
-- introspect it at definition time, read fields during translation,
build a fresh instance at the end -- goes through one of those three
methods.

Betwixt ships built-in adapters for stdlib `@dataclass`, Pydantic
`BaseModel`, `attrs`, and `msgspec`. Choosing one is implicit:
when you write `left = UserRow`, Betwixt looks up the right
adapter for `UserRow`'s class and uses it. There is no `adapter=`
kwarg on the Betwixt model body for the common case.

For types Betwixt doesn't know about -- SQLAlchemy ORM classes,
Protobuf messages, custom `__slots__` types, anything else -- the
user implements the Protocol once for that type and registers it.
After registration, that type is indistinguishable from a built-in
side as far as the rest of Betwixt is concerned.

The built-in adapters use the same Protocol the user would. There
is no privileged "real" Pydantic support and "lesser" external
support. If a user's custom adapter is faster or smarter than a
built-in, they can replace the built-in. The Protocol is the only
contract.

----

## Betwixt

A `Betwixt` is the central object of this library. It is a class that
declares the relationship between two structured types -- here `UserRow`
(the **left** side, a stdlib `@dataclass`) and `UserResponse` (the
**right** side, a Pydantic `BaseModel`) -- and provides two methods,
`leftward` and `rightward`, that translate instances of one side into
instances of the other.

The body of a `Betwixt` subclass is a complete, symmetric account of how
the two types correspond. Reading it is reading the spec.

```python
from betwixt import (
    Betwixt, f,
    map_pairwise, map_rightward, map_leftward,
    reduce_rightward, reduce_leftward,
    project_rightward, project_leftward,
    default_rightward, default_leftward,
)
import pendulum


class UserBetwixt(Betwixt):
    left = UserRow
    right = UserResponse

    # Field-reference aliases. f(SomeType) returns a typed accessor proxy
    # that yields a FieldRef for any attribute access. The L/R convention
    # makes the directional structure of every declaration visible at a
    # glance: left=L.x, right=R.y reads as a parallel construction.
    L, R = f(left), f(right)

    # --- 1:1 by name+type: NO declaration needed for `tags`, `created_at` ---

    # --- Symmetric map_pairwise: invertible rename --------------------------
    email = map_pairwise(
        left=L.email_address,
        right=R.email,
    )

    # --- Symmetric map_pairwise: invertible transform (rename + type coercion) ---
    id = map_pairwise(
        left=L.id,
        right=R.id,
        rightward=lambda db_id: f"usr_{db_id:08d}",
        leftward=lambda api_id: int(api_id.removeprefix("usr_")),
    )

    # --- Asymmetric: combining is NOT naturally invertible ------------------
    # rightward direction: combine first_name + last_name into full_name.
    full_name_rightward = map_rightward(
        left=(L.first_name, L.last_name),
        right=R.full_name,
        rightward=lambda first, last: f"{first} {last}",
    )
    # leftward direction: split full_name back. Stated independently because
    # the rule is lossy and the user must own that decision explicitly.
    full_name_leftward = map_leftward(
        left=(L.first_name, L.last_name),
        right=R.full_name,
        leftward=lambda full: tuple(full.split(" ", 1)) if " " in full else (full, ""),
    )

    # --- Right field reduced from the whole left object ---------------------
    # `reduce_rightward`: the rightward function takes the whole UserRow
    # and produces the value of one right-side field. Useful when the
    # field's computation depends on multiple (or all) left-side fields,
    # and there is no meaningful leftward direction because the field
    # does not exist on the left side at all.
    #
    # When a function needs runtime data that lives on neither side
    # (here: "now"), it accepts an extra `ctx` parameter as its last
    # positional argument. The caller supplies a `context` dict at
    # translation time and the framework threads it through. Calling
    # pendulum.now() inline would hide the dependency and break test
    # reproducibility; pulling it from `ctx` makes "this is recent *as
    # of when?*" an explicit input.
    is_recent = reduce_rightward(
        right=R.is_recent,
        rightward=lambda row, ctx: (ctx["now"] - row.created_at).days < 7,
    )

    # --- Left-only fields: no rightward writer, so we need a default --------
    # when going leftward. Construct name carries the direction; `left=`
    # identifies the field; `default=` is the value (or `...` to mean
    # "required at call time", or a zero-arg callable for late-bound
    # construction such as `default=list` or `default=lambda: pendulum.now()`).
    # If you need a default that depends on the right-side object being
    # translated, use `reduce_leftward` instead -- that is precisely what
    # it is for, and overlapping the two would be a category error.
    password_hash = default_leftward(
        left=L.password_hash,
        default=...,  # required: caller must supply when going leftward
    )
    internal_note = default_leftward(
        left=L.internal_note,
        default="",
    )
```


### Reading the spec

Every construct in the library is named `<verb>_<direction>`. The verb
says what the construct *does* (in terms of input arity → output arity);
the direction says when it runs.

#### Verbs (the prefix)

The verb names what the construct *does* in terms of input arity ->
output arity. Each verb fills exactly one cell in the input/output
space; the cells without a verb (e.g. taking named fields and
producing a whole object) are not meaningful and have no construct.

| Verb        | Input                       | Output                      | What it does                                                                          |
|-------------|-----------------------------|-----------------------------|---------------------------------------------------------------------------------------|
| `map_*`     | one or more named fields    | one named field             | Translate named field(s) on one side to a named field on the other side.              |
| `reduce_*`  | the whole opposite object   | one named field             | Reduce the whole opposite-side object down to one field's worth of value on this side.|
| `project_*` | the whole opposite object   | the whole this-side object  | Build the whole this-side object from scratch in one function call.                   |
| `nested_*`  | one named field             | one named field             | Delegate the field's translation to another `Betwixt` subclass, named via `via=`.     |
| `default_*` | (none)                      | one named field             | Supply a default value for a field that no translation function fills.                |

The trivial 1:1 case for `map_*` (same name, same type, no transform)
is implicit and needs no declaration at all.

`default_*` is narrowly about defaulting: the `default=` kwarg accepts
a value, `...` to mean "must be supplied at the call site," or a
zero-arg callable for late binding (`default=list`,
`default=lambda: pendulum.now()`). If you want a default whose value
depends on the opposite-side object being translated, that is
`reduce_*`, not `default_*`. Keeping these two non-overlapping is
deliberate: `default_*` is for *gaps*, `reduce_*` is for *computations*.

Any function-taking construct (`map_*`, `reduce_*`, `project_*`) can
also opt into receiving a **runtime context** dict by accepting a
final `ctx` parameter. See [Runtime context](#runtime-context) below.


#### Directions (the suffix)

- **`_rightward`** -- runs only when going left → right.
- **`_leftward`** -- runs only when going right → left.
- **`_pairwise`** -- both directions, declared together. Available for
  `map_*` and `nested_*`. The bundling is meaningful when the two
  directions share a *field anchor* (same field on both sides). For
  `reduce_*`, `project_*`, and `default_*` there is no such anchor:
  each direction stands alone with its own input and output, so the
  library deliberately omits `reduce_pairwise`, `project_pairwise`,
  and `default_pairwise`. If you want both directions for one of
  these, declare them as two independent attributes.


#### Full construct table

| Construct           | Directions | Input (one direction)                              | Output (one direction)                       |
|---------------------|------------|----------------------------------------------------|----------------------------------------------|
| (omitted)           | both       | one named field                                    | one named field                              |
| `map_pairwise`      | both       | one or more named fields                           | one named field                              |
| `map_rightward`     | rightward  | one or more named left fields                      | one named right field                        |
| `map_leftward`      | leftward   | one or more named right fields                     | one named left field                         |
| `reduce_rightward`  | rightward  | the whole left object                              | one named right field                        |
| `reduce_leftward`   | leftward   | the whole right object                             | one named left field                         |
| `project_rightward` | rightward  | the whole left object                              | the whole right object                       |
| `project_leftward`  | leftward   | the whole right object                             | the whole left object                        |
| `nested_pairwise`   | both       | one named field (delegates to inner betwixt)       | one named field (delegates to inner betwixt) |
| `nested_rightward`  | rightward  | one named left field (delegates to inner betwixt)  | one named right field                        |
| `nested_leftward`   | leftward   | one named right field (delegates to inner betwixt) | one named left field                         |
| `default_rightward` | rightward  | -- (provides a default)                            | -- (declares a side-only field)              |
| `default_leftward`  | leftward   | -- (provides a default)                            | -- (declares a side-only field)              |

When you declare a `map_pairwise(...)` with both `rightward` and
`leftward` functions, you must supply both. There is no implicit
inversion. If a transform happens to be mathematically invertible, that
is your problem to verify, not the library's to assume.

When the rule genuinely differs in each direction (combining vs.
splitting, hashing vs. nothing), pairing a `map_rightward` with a
`map_leftward` declaration makes the asymmetry load-bearing and visible.
You cannot hide it.


### Universal rule: every translation function is named by its direction

Every callable that participates in a translation is passed as either
`rightward=` or `leftward=`. There are no directionless translation
functions in this library. The construct (`map_pairwise`, `map_rightward`,
`map_leftward`, `reduce_rightward`, `reduce_leftward`, `project_rightward`,
`project_leftward`) describes the *shape* of the relationship; the kwarg
name describes the *direction* the function implements.

This is not just consistency for its own sake. The translation engine
collects, for each direction, every declaration that contributes to that
direction and runs them in order. For a rightward conversion, that
means gathering:

- every `rightward=` function from `map_rightward`, `reduce_rightward`,
  and `project_rightward` declarations,
- the `rightward=` half of every `map_pairwise` declaration,
- and the `default=` value (or factory) from every `default_rightward`
  declaration -- filling right-side fields that no translation function
  produces.

Leftward conversion is symmetric. The implementation is essentially:

> "Walk the Betwixt model. For each declaration that contributes to this
> direction, run its rightward (or leftward) callable, or apply its
> default. Assemble the resulting fields into an instance of the target
> side."

If some functions were directionless and others weren't, the engine
would have to inspect each construct's target to figure out which
bucket the function belongs in. Tagging the function directly removes
that whole class of branching, both in the implementation and in the
mental model a reader has to build.

The corollary: a `project_rightward` declaration has no leftward
counterpart by construction -- the construct's name says it builds the
right side from the left, full stop. The reader does not have to scan
kwargs to learn this; the name carries it.


### Runtime context

Most translation functions are *closed*: their inputs come entirely
from the source-side object. To produce `R.full_name` from
`L.first_name` and `L.last_name`, the function needs nothing else.

Some translations are not closed. They need a piece of information
that lives on **neither side** and varies **per call**:

- An FX rate to convert `amount_minor` to `amount_usd`.
- The current time, to compute `is_recent` reproducibly.
- The requesting user's identity, to compute `can_edit`.
- A locale, to format a price string.
- A feature flag, to decide whether to populate a field at all.

Betwixt names this third source of inputs **context**. The caller
supplies it as a dict at translation time:

```python
response = UserBetwixt.rightward(row, context={"now": pendulum.now()})
```

The dict's keys are arbitrary strings agreed on between the caller
and the constructs that consume them. The values are whatever the
constructs need -- a `pendulum.DateTime`, an FX-rate dict, an
authenticated user object, a locale string.

A construct that needs context simply accepts an extra parameter --
conventionally named `ctx` -- as the **last positional argument** of
its translation function. The framework looks at the function's
signature once, at construct-definition time, and remembers whether
to pass `ctx` to it on each call.

```python
is_recent = reduce_rightward(
    right=R.is_recent,
    rightward=lambda row, ctx: (ctx["now"] - row.created_at).days < 7,
)
```

That is the entire mechanism. There is no separate declaration
listing which keys the function uses; the function's body shows them
directly (`ctx["now"]`). Functions that don't need context don't
mention it:

```python
full_name_rightward = map_rightward(
    left=(L.first_name, L.last_name),
    right=R.full_name,
    rightward=lambda first, last: f"{first} {last}",   # no ctx; no problem
)
```

Multiple lookups from the same `ctx` are just... multiple lookups,
nothing special:

```python
amount_usd_rightward = map_rightward(
    left=(L.amount_minor, L.currency),
    right=R.amount_usd,
    rightward=lambda minor, ccy, ctx: (
        to_major(minor, ccy) * ctx["fx_rates"][ccy]
    ).quantize(Decimal("0.01")),
)
```

If a function tries to look up a key the caller didn't provide, the
result is a regular `KeyError` with the missing key's name in the
message and the lookup line in the traceback. Clear enough; no
framework-level pre-validation needed.


#### Why this is its own thing, not just a closure

A translation function is a Python callable. It can already close
over module-level state, call other functions, or do I/O inline. So
why does Betwixt route runtime data through `ctx` instead of letting
functions reach for it themselves?

Because the alternatives degrade the design:

- **Inline I/O inside the function** (`pendulum.now()` in the lambda
  body) hides the dependency from anything outside the function. Two
  calls produce different results with no input difference. Tests
  must monkeypatch.
- **Module-level mutable state** is thread-unsafe and order-dependent.
  Setting a "current FX rate" global before each translation is the
  kind of code that produces 2am pages.
- **Stuffing the value onto a side type** (adding `_fx_rates` to
  `PaymentRow`) pollutes the type with information that has nothing
  to do with what the type represents. This is the model-stuffing
  failure mode that the whole library exists to prevent; it would
  be perverse for Betwixt to push users into it.

Routing runtime data through `ctx` makes the dependency **a
parameter of the function**: visible in its signature, supplied by
the caller, isolated per-call, threaded explicitly. The function
remains a pure transformation of its inputs; the inputs just include
"the runtime context this translation is happening in."

Static helpers (`MINOR_UNITS`, `to_major`, `pendulum`, etc.) stay as
ordinary closures because they don't vary per call. `ctx` is for
*per-call-varying* values only.


#### Typing the context

The baseline contract is "`ctx` is a `dict[str, Any]`." That always
works, requires zero declaration, and is the right starting point
when the context is small or the Betwixt model is throwaway.

When the context grows, the user can opt into a typed context. The
mechanism is purely conventional: declare the context shape using
whatever typing tool the rest of the project already uses, and pass
an instance of that type as `context=...`.

The most lightweight option is `TypedDict`:

```python
class UserContext(TypedDict):
    now: pendulum.DateTime

response = UserBetwixt.rightward(row, context=UserContext(now=pendulum.now()))
```

A type checker now knows the shape and will catch a typo or a
missing key at the call site. Nothing in Betwixt's runtime behavior
changes.

For a larger context, a dataclass or attrs class works equally
well:

```python
@dataclass
class UserContext:
    now: pendulum.DateTime
    fx_rates: dict[str, Decimal]
    requesting_user: User

response = UserBetwixt.rightward(row, context=UserContext(...))
```

Same for a Pydantic `BaseModel`, `msgspec.Struct`, or any other
type-modeling library: pass an instance, the function reads it
however that type is read.

Betwixt does not introspect the context, validate it, or care what
shape it is. The `context=` value is passed through to the function
unchanged, and the function uses whatever access style is correct
for the type the caller passed.

Whether a typed context is the right move depends on context size
and reuse. For a one-off lambda that needs `now`, the untyped dict
is fine. For a betwixt threaded through multiple call sites with
five distinct context keys, declaring the shape once pays for
itself.

----

### Translation semantics

A betwixt body can declare any mix of `map_*`, `reduce_*`,
`project_*`, `nested_*`, and `default_*` constructs in either
direction. Some combinations have obvious non-overlap (a
`map_rightward` writing `R.email` and another writing `R.full_name`).
Others overlap by construction: a `project_rightward` builds the
whole right-side object, and any field-level construct in the same
direction writes to a field the projection has already produced. A
`reduce_rightward` that aggregates `L.tags` into `R.tag_summary`
and a `map_rightward` that also writes `R.tag_summary` clobber each
other.

Trying to detect overlap automatically is a losing game. A
`project_rightward` callable is opaque; the framework cannot tell
which fields it actually populates without running it (and even then
"populated" is a fuzzy notion when defaults are involved). Same
problem for `reduce_*` and any user-supplied function. Building a
static analyzer that introspects function bodies to predict their
write set is exactly the kind of compiler-grade machinery that
violates the design principle of staying small.

So Betwixt picks the simple, predictable rule and gets out of the
way:


#### Translations apply in declaration order

Constructs run in the order they appear in the Betwixt class body.
Each construct that writes to a right-side field overwrites whatever
a previous construct wrote to that field. Last write wins. This is
the order Python already preserves in class `__dict__` (since 3.7),
so the rule needs no extra machinery and matches what a reader
already sees on the page.


#### Overlap is a user responsibility, not a framework concern

Betwixt does not validate that two constructs avoid each other's
fields. It does not warn when a later declaration overwrites an
earlier one. It does not introspect projection or reduction
functions to predict their write sets. If two constructs touch the
same field, the second one wins, and the user is responsible for
knowing whether that was intended.

This sounds permissive, but it composes cleanly with the most
common use case: a `project_rightward` that builds a baseline
right-side object, followed by a few `map_rightward` declarations
that override specific fields where the projection's output isn't
quite right. Same shape as a dict literal followed by item
assignments. Users who want stricter discipline can write a test
that round-trips a representative instance and compares the result
to a hand-built expected value. The framework stays out of the way.


#### Attribute names are labels

The attribute name a construct is bound to is a label for humans.
Betwixt does not parse it, does not require a particular suffix, and
does not match it against side-field names. A `map_pairwise` whose
construct happens to be named `email` writes to whatever right-side
and left-side fields the construct itself declares (`right=R.email`
and `left=L.email_address`); the attribute name `email` is just
where the user chose to put it. The same goes for `project_*` and
`reduce_*`: they have no per-field anchor, so the attribute name has
nothing to anchor to either. Pick a name that reads well next to the
other declarations and move on.

The `<name>_rightward` / `<name>_leftward` suffix convention used
throughout this document is exactly that: a convention. It pairs
visually-related declarations on the page so a reviewer can see at a
glance that two halves of an asymmetric transform belong together.
The framework doesn't enforce it, and the framework doesn't need to.


### Nested betwixts

If `UserRow.addresses: list[AddressRow]` pairs with
`UserResponse.addresses: list[AddressResponse]`, the user shouldn't
have to manually wire up the inner translation. Some other betwixt
in the project, `AddressBetwixt`, already knows how to translate
`(AddressRow, AddressResponse)`. The mechanism for reusing it
should be ergonomic without smuggling in import-order or
declaration-order dependencies.


#### Three constructs paralleling `map_*`

The three nested constructs match the `map_pairwise` /
`map_rightward` / `map_leftward` shape exactly. Each takes a `via=`
kwarg pointing at the inner `Betwixt` subclass to invoke:

```python
class UserBetwixt(Betwixt):
    left = UserRow
    right = UserResponse
    L, R = f(left), f(right)

    # Both directions: rightward translates AddressRow -> AddressResponse,
    # leftward translates AddressResponse -> AddressRow.
    addresses = nested_pairwise(
        left=L.addresses,
        right=R.addresses,
        via=AddressBetwixt,
    )

    # Rightward only: AuditLogEntry -> AuditLogResponse, no inverse.
    audit_log_rightward = nested_rightward(
        left=L.audit_log_entries,
        right=R.audit_log,
        via=AuditLogBetwixt,
    )

    # Leftward only: SettingsResponse -> SettingsBlob, no inverse.
    settings_leftward = nested_leftward(
        right=R.settings,
        left=L.settings_blob,
        via=SettingsBetwixt,
    )
```

The `via=` argument is a real class reference, which Python forces
the user to import explicitly. If the import is missing, you get a
plain `NameError` at the line of source you are looking at.
Circular-import problems get solved the same way they always do in
Python: a `TYPE_CHECKING` block, a local import inside a method, or
a module restructure.


#### Container traversal

Each `nested_*` construct understands the common container shapes
natively:

| Annotation pair                                          | Behavior                               |
|----------------------------------------------------------|----------------------------------------|
| `AddressRow` / `AddressResponse`                         | Translate the single value             |
| `list[AddressRow]` / `list[AddressResponse]`             | Translate each element                 |
| `tuple[AddressRow, ...]` / `tuple[AddressResponse, ...]` | Translate each element                 |
| `dict[K, AddressRow]` / `dict[K, AddressResponse]`       | Translate each value, keys passthrough |
| `set[AddressRow]` / `set[AddressResponse]`               | Translate each element                 |
| `AddressRow \| None` / `AddressResponse \| None`         | Translate if not None                  |

The framework uses `typing.get_origin()` / `get_args()` to walk the
annotations on both sides. Container shape must agree across the
two sides; you cannot go `list[AddressRow]` to `set[AddressResponse]`
without an explicit `map_*`.

Anything more exotic needs an explicit `map_*` or `project_*`
construct. This includes custom containers, lazy collections, ORM
relationship proxies, generic containers the project owns
(`Repository[AddressRow]` paired with `Repository[AddressResponse]`),
and **discriminated unions and `RootModel` types**. The framework
doesn't try to be clever about any of these.

For a discriminated union field, write a `map_*` whose function
dispatches on `type()` (or `match`) and delegates to the right
sub-betwixt:

```python
event_rightward = map_rightward(
    left=L.event,
    right=R.event,
    rightward=lambda ev: (
        PaymentEventBetwixt.rightward(ev)
        if isinstance(ev, PaymentEvent)
        else RefundEventBetwixt.rightward(ev)
    ),
)
```

For a `RootModel[X]`, refer to the `.root` attribute inside a
`map_*` or `project_*` and translate the wrapped value directly.
Betwixt does not unwrap `RootModel` automatically; the unwrap is
one line of user code at the boundary.

The principle: Betwixt's first-class shapes are the ones with an
unambiguous one-to-one structural correspondence across both sides.
Discriminated unions need per-case dispatch logic, which is exactly
what `map_*` is for. Building a declarative form for unions would
make Betwixt grow Pydantic-specific machinery that doesn't earn its
weight.


#### Element type validation

At outer-betwixt definition time, the framework checks that
`via=AddressBetwixt`'s `left` and `right` types match the element
types of the field references on the matching sides. A mismatch
raises immediately:

```python
addresses = nested_pairwise(
    left=L.addresses,    # list[AddressRow]
    right=R.addresses,   # list[AddressResponse]
    via=AccountBetwixt,  # left=AccountRow, right=AccountResponse
)
# raises: AccountBetwixt translates (AccountRow, AccountResponse),
# but UserBetwixt.addresses needs (AddressRow, AddressResponse)
```

This is a definition-time check, not a translation-time check, so
the error fires the moment the outer betwixt's module is imported.


#### Context propagation

A nested betwixt is invoked the same way any other betwixt is
invoked: someone calls its `rightward` or `leftward` method with an
instance and a `context=...` value. When that someone is the outer
betwixt's machinery (rather than the user directly), the question is
where the inner's context comes from.

The answer: the outer declares it, per `nested_*` construct. Each
nested construct accepts `context_pairwise=`, `context_rightward=`,
or `context_leftward=` -- callables that take the outer's `context`
and return the inner's `context`:

```python
class UserBetwixt(Betwixt):
    left = UserRow
    right = UserResponse
    L, R = f(left), f(right)

    addresses = nested_pairwise(
        left=L.addresses,
        right=R.addresses,
        via=AddressBetwixt,
        context_rightward=lambda ctx: {"geocoder": ctx["geocoder"]},
    )

    is_recent = reduce_rightward(
        right=R.is_recent,
        rightward=lambda row, ctx: (ctx["now"] - row.created_at).days < 7,
    )
```

A caller invokes:

```python
response = UserBetwixt.rightward(
    user_row,
    context={"now": pendulum.now(), "geocoder": geocoder},
)
```

Reading the outer body tells you everything the call needs. `now`
is consumed directly by `is_recent`. `geocoder` is consumed by the
nested `AddressBetwixt`, declared at the `addresses` line via
`context_rightward`. No spelunking into `AddressBetwixt` is required
to know what to pass at the call site.

If a nested construct omits `context_rightward=` (or
`context_leftward=`, or `context_pairwise=`), the inner betwixt is
invoked with `context=None`. If the inner has any function that
reads `ctx[...]`, the call fails at the lookup line, and the
traceback points at both the lookup and the outer `nested_*` line
that fired it. There is no implicit pass-through and no sentinel:
if you want to pass the outer's context through unchanged, write
`context_rightward=lambda ctx: ctx`. The verbosity is the point --
a `nested_*` declaration with no `context_*=` line means "the inner
gets nothing," visibly.

The shape mirrors the `map_pairwise` / `map_rightward` /
`map_leftward` direction split: `context_pairwise=` for the
single-callable case, the directional variants when the two
directions need different context shapes (or when one direction
needs no context and the other does).


### Why field references go through `f()`

Betwixt declarations refer to fields through `f(SomeType).field_name`
rather than through string literals (`"field_name"`) or bare attribute
access (`SomeType.field_name`). The first sub-question is *why
attribute-style references at all?*. The second is *why a wrapper
(`f(...)`) instead of bare attributes?*


#### Why attribute-style references instead of strings

Field references like `f(UserRow).email_address` resolve to typed
`FieldRef` objects rather than opaque string keys. This buys:

- **Static checking.** A typo (`f(UserRow).emial_address`) is caught at
  betwixt-construction time, when the `Betwixt` subclass body executes --
  not later, the first time the Betwixt model is exercised. (A type-checker
  plugin or PEP 747 `TypeForm` could push this further to *static*
  catch; until then, the construction-time check is the floor.)
- **Refactor safety.** Renaming a field via an IDE updates every
  reference automatically, because the IDE understands attribute
  access. String-based specs require text search-and-replace, which
  silently drifts.
- **Jump-to-definition.** `f(UserRow).email_address` is navigable in
  any IDE; `"email_address"` is not.
- **Single source of truth.** The side type owns the field name; the
  betwixt references it. String-based specs duplicate the name on every
  declaration.


#### Why `f(...)` instead of bare attributes

Most structured-type libraries in Python -- including stdlib
`@dataclass` and Pydantic's `BaseModel` -- do **not** expose fields as
class attributes. `UserRow.email_address` raises `AttributeError` on a
plain dataclass with no default; `UserResponse.email` raises
`AttributeError` on a Pydantic model regardless of default. The field
information is available (in `__dataclass_fields__` or `model_fields`),
just not through plain attribute access.

`f(...)` is Betwixt's universal accessor that bridges this gap without
modifying the underlying type:

```python
from betwixt import f

class UserBetwixt(Betwixt):
    left = UserRow
    right = UserResponse
    L, R = f(left), f(right)   # plain @dataclass and Pydantic both work

    email = map_pairwise(left=L.email_address, right=R.email)
    ...
```

`f(SomeType)` returns a proxy whose attribute access yields a typed
`FieldRef`. The proxy dispatches on the type's introspection protocol:
`__dataclass_fields__` for stdlib dataclasses, `model_fields` for
Pydantic, equivalent attributes for `attrs` and `msgspec`, and a public
adapter protocol for anything else.

The cost is two extra characters per reference (`L.x` vs `UserRow.x`)
and one declaration line at the top of each betwixt (`L, R = f(left),
f(right)`). The benefit is that Betwixt is **completely non-invasive on
both sides**: the user's `@dataclass`, `BaseModel`, `attrs.define`d
class, or `msgspec.Struct` is untouched. Betwixt adds nothing to the
type definitions; the relationship lives entirely in the Betwixt body.

This non-invasiveness is the whole point of design principle 2 (*the
mapping layer, nothing else*). A decorator that augmented the side
types -- "use `@betwixt_dataclass` instead of `@dataclass`" -- would
violate it. `f(...)` is what makes the principle real.


#### The alias convention

Every betwixt example in this document opens with:

```python
class SomeBetwixt(Betwixt):
    left = SomeLeft
    right = SomeRight
    L, R = f(left), f(right)

    # ... declarations using L.x and R.y
```

The class-level `left = ...` and `right = ...` attributes are real
API: they tell Betwixt which two types the Betwixt model translates
between. The `L, R = f(left), f(right)` line is recommended idiom,
not API. It exists purely to keep declarations short and to make
directional structure visually obvious: `left=L.foo, right=R.bar`
reads as a parallel construction. The line works because the class
body is an ordinary Python namespace during construction; by the
time `L, R = f(left), f(right)` runs, `left` and `right` are already
bound from the lines above. There is no requirement to use the short
names `L` and `R`; they are just short, mnemonic, and uniform across
examples.

----

## Using Betwixt

A `Betwixt` subclass exposes exactly two methods: `leftward` and
`rightward`. Each takes an instance of one side and returns an instance
of the other. That is the entire user-facing API surface for
translation.

```python
import dataclasses
import pendulum

# 1. Validate untrusted input. This is Pydantic's job, not Betwixt's.
api_json = {
    "id": "usr_00000042",
    "full_name": "Ada Lovelace",
    "email": "ada@example.com",
    "tags": ["admin"],
    "created_at": "2024-01-15T10:30:00Z",
    "is_recent": True,
}
response = UserResponse.model_validate(api_json)         # UserResponse instance

# 2. Translate via the Betwixt model. Direction is named at the call site.
#    Leftward needs no context here -- none of the leftward functions
#    accept a `ctx` parameter. Rightward needs context because
#    `is_recent`'s lambda accepts `ctx` and reads `ctx["now"]` from it.
row = UserBetwixt.leftward(response)                       # UserRow instance
# To go the other way:
response_again = UserBetwixt.rightward(
    row,
    context={"now": pendulum.now()},
)                                                        # UserResponse instance

# 3. Serialize. Each side uses its own native serialization machinery.
api_payload = response.model_dump_json()                 # Pydantic does this
db_dict     = dataclasses.asdict(row)                    # stdlib does this
```

Now, here are four key observations about Betwixt:


#### Betwixt does not validate

When you load `api_json` into a
`UserResponse`, you call `UserResponse.model_validate(...)` -- Pydantic.
Pydantic does the JSON parsing, the type coercion, the per-field
validators, the error message formatting, and the JSON Schema
generation. None of that is Betwixt's responsibility, and Betwixt does not
duplicate any of it. If validation fails, you get a `ValidationError`
from Pydantic with all of Pydantic's error-path machinery intact.

This includes wire-format aliases. If `UserResponse.email_address`
is declared with `Field(alias="email")`, Pydantic resolves the
incoming JSON key `"email"` to the Python attribute `email_address`
during `model_validate`. By the time Betwixt sees the instance, only
the attribute name exists. Betwixt always refers to fields by their
Python attribute name (`R.email_address`); aliases never reach the
betwixt body.


#### Betwixt does not serialize

When you turn a `UserResponse` into a
JSON payload, you call `response.model_dump_json()` -- again Pydantic.
When you turn a `UserRow` into a dict, you use
`dataclasses.asdict(row)` -- stdlib. If you wanted YAML, you'd reach
for the YAML library that you already use for everything else. Betwixt
has no opinions about your serialization stack.


#### Betwixt does the translation step

Given a validated instance of one
side, produce an instance of the other side, applying every declaration
in the Betwixt model body. That is the one job. The whole library exists for
this single step in the three-step flow, because it is the step
nothing else does well.


#### Translation can require runtime context

Some declarations consume
per-call values that live on neither side -- `pendulum.now()` here, an
FX rate for a payment, the current user for an authorization decision.
A function opts into receiving these by accepting a final `ctx`
parameter; the caller passes a matching `context={...}` dict at
translate time. See [Runtime context](#runtime-context).

This focus is what makes Betwixt small. There is no `load_left()`,
`load_right()`, `dump_left()`, `dump_right()`, no `format=` kwarg, no
codec registry, no `class Meta` block. The validation-and-serialization
machinery you already trust stays in place; Betwixt slots in between.

----

## Partial / patch translations

PATCH-style APIs send partial updates. A client sends `{"full_name":
"Lando Calrissian"}` to change one field on an existing user; the
server validates that into a sparse `UserResponse` (or a sibling
`UserUpdate` model with everything optional) and needs to translate
it to the database side. The output cannot be a `UserRow` instance,
because `UserRow` has required fields the client did not supply. The
output should be a dict of patches that the persistence layer can
apply with `UPDATE users SET ... WHERE id = ...`.

A `Betwixt` subclass exposes two additional methods for this case:
`leftward_partial` and `rightward_partial`. Each takes a dict and
returns a dict.

```python
patches = UserBetwixt.leftward_partial(
    {"full_name": "Lando Calrissian"},
)
# patches == {"first_name": "Lando", "last_name": "Calrissian"}

patches = UserBetwixt.rightward_partial(
    {"email_address": "lando@cloud-city.bespin"},
)
# patches == {"email": "lando@cloud-city.bespin"}
```

Input can be a raw dict or a model instance with absent fields
marked unset (Pydantic's `model_dump(exclude_unset=True)` produces
the right dict). Output is always a dict, and the dict only
contains keys the constructs were able to derive from the input.

### Per-construct semantics on partial input

| Construct                        | Behavior on partial                                                                                   |
|----------------------------------|-------------------------------------------------------------------------------------------------------|
| `map_pairwise`                   | Runs if all source-side inputs are present; otherwise omitted                                         |
| `map_rightward` / `map_leftward` | Same as `map_pairwise` (relevant direction only)                                                      |
| `reduce_*`                       | Runs if all declared source inputs are present; otherwise omitted                                     |
| `project_*`                      | Runs unconditionally; receives a partial source object as input                                       |
| `nested_*`                       | Runs if the source-side field is present; delegates to the inner betwixt's matching `_partial` method |
| `default_*`                      | Skipped entirely on partial translations                                                              |

The first five follow the same rule: a construct runs when its
declared inputs are all available, and contributes nothing
otherwise. The `default_*` row is the interesting one. Defaults are
for *gaps in a full translation*: a database needs `password_hash`,
the API doesn't provide one, the Betwixt model fills the gap. A partial
translation is not a full translation; the caller is explicitly
saying "I'm not telling you about every field." Firing defaults
into the patch dict would push values the caller didn't ask for
into the `UPDATE` statement, which is silently destructive. So
defaults skip on partial.

### Worked example

The same `UserBetwixt` body works for both modes, no new
declarations:

```python
class UserBetwixt(Betwixt):
    left = UserRow
    right = UserResponse
    L, R = f(left), f(right)

    full_name_leftward = map_leftward(
        right=R.full_name,
        left=(L.first_name, L.last_name),
        leftward=lambda full: tuple(full.split(" ", 1)),
    )
    email_leftward = map_leftward(
        right=R.email,
        left=L.email_address,
        leftward=lambda e: e,
    )
    password_hash_leftward = default_leftward(
        left=L.password_hash,
        default=lambda ctx: ctx["new_password_hash"],
    )

# Full leftward: every construct fires, including the default
row = UserBetwixt.leftward(
    response,
    context={"new_password_hash": "<hash>"},
)
# row is a complete UserRow

# Partial leftward: only constructs whose inputs are present fire
patches = UserBetwixt.leftward_partial({"full_name": "Lando Calrissian"})
# patches == {"first_name": "Lando", "last_name": "Calrissian"}
# password_hash NOT in patches because default_leftward skips on partial
# email NOT in patches because email_leftward's input is absent
```

### Why a separate method instead of a flag

`leftward(..., partial=True)` would change the return type based on
a kwarg (`UserRow` vs `dict`), which is awkward for callers and
type checkers. A separate `leftward_partial` method has a stable
return type (`dict[str, Any]`) and signals at the call site that
the caller is in patch-mode. The two methods share all the
construct dispatch machinery internally; only the "missing input
omits the construct" rule differs.

### What counts as "present"

Betwixt sees a dict. A key absent from the dict means the field is
not present; a key set to `None` means the field is present and its
value is `None`. The caller is responsible for normalizing
"client did not mention this field" to "key absent" before calling
`leftward_partial` or `rightward_partial`.

This pushes the "did the client mean *clear this field* or *I'm
not telling you about this field*?" question out of Betwixt's
scope, where it belongs: that's a wire-format and validation
concern. Pydantic's `Unset` sentinel, FastAPI's `exclude_unset=True`,
or any equivalent normalization at the edge produces the dict
shape Betwixt expects. Betwixt itself stays out of that
distinction.

----

## Pydantic alone vs. Pydantic + Betwixt

The setup so far has assumed Betwixt is *added to* a stack that already
includes Pydantic. The fair comparison, then, is not "Betwixt instead of
Pydantic" but "what happens if you try to express this same scenario
using only Pydantic, with no separate mapping layer."

This is the path most Pydantic users actually walk: they make their
API model do double duty as both the wire-format validator *and* the
mapping layer to their persistence type. The result is a model that is
secretly two models tied together with conditional logic.


### Without Betwixt: one Pydantic model, two roles

A typical Pydantic-only solution to the same scenario looks something
like this. It works, but every piece of asymmetry between `UserRow`
and the API representation has to be smuggled into the single
`UserResponse` model:

```python
from dataclasses import dataclass
from pydantic import BaseModel, Field, computed_field, model_validator
import pendulum

@dataclass
class UserRow:
    id: int
    first_name: str
    last_name: str
    email_address: str
    password_hash: str
    internal_note: str
    tags: list[str]
    created_at: pendulum.DateTime


class UserResponse(BaseModel):
    # Aliasing because the wire format renames `email_address` -> `email`.
    # populate_by_name=True is needed so the model can accept either name
    # depending on which direction it's being used.
    model_config = {"populate_by_name": True}

    id: str
    full_name: str
    email: str = Field(
        validation_alias="email_address",
        serialization_alias="email",
    )
    tags: list[str]
    created_at: pendulum.DateTime

    @model_validator(mode="before")
    @classmethod
    def _coerce_from_row(cls, data):
        # Detects "this looks like it came from a UserRow" and rewrites
        # the dict to match the API shape. Pure pattern-sniffing; brittle.
        if isinstance(data, dict) and "first_name" in data:
            data = dict(data)
            data["full_name"] = (
                f"{data.pop('first_name')} {data.pop('last_name', '')}".strip()
            )
            data["id"] = f"usr_{data['id']:08d}"
        return data

    @computed_field
    @property
    def is_recent(self) -> bool:
        return (pendulum.now() - self.created_at).days < 7

    # The OTHER direction (API -> DB) is a hand-rolled method, because
    # Pydantic has no first-class concept of bidirectional mapping. It
    # lives next to the model only by convention.
    def to_row(
        self,
        *,
        password_hash: str,
        internal_note: str = "",
    ) -> UserRow:
        first, _, last = self.full_name.partition(" ")
        return UserRow(
            id=int(self.id.removeprefix("usr_")),
            first_name=first,
            last_name=last,
            email_address=self.email,
            password_hash=password_hash,
            internal_note=internal_note,
            tags=self.tags,
            created_at=self.created_at,
        )
```


### What's wrong with this picture

The problems are not Pydantic's fault. Pydantic is doing exactly what
it advertises: it validates and serializes a single model. The mismatch
is that the user is asking it to do something it was not built for --
to be a mapping layer between two distinct types -- and the result is
an accumulation of small uglinesses, none individually severe but
collectively suffocating:


#### The Pydantic model is no longer just an API contract

A clean API model describes one thing: the shape clients see on the
wire. This `UserResponse` describes that, plus the shape of a
`UserRow`, plus the rules for converting between them. The
`_coerce_from_row` validator is row-aware: it knows that `first_name`
and `last_name` exist on the database side and that they combine
into `full_name` on the API side. That knowledge has nothing to do
with the API contract, but it lives inside the model that defines
the API contract. Anyone reading `UserResponse` to understand what
the API returns has to filter out the half of the body that isn't
about the API at all.


#### `populate_by_name=True` is a wire-protocol concession

The `email` field uses both `validation_alias="email_address"` and
`serialization_alias="email"` so the same model can be fed a row
dict (which has `email_address`) and produce a wire payload (which
has `email`). The `populate_by_name=True` config exists to make
that dual identity work. None of this is about the API contract;
it is wire-protocol gymnastics performed in service of a mapping
problem. A field that has only ever had one name on the wire now
carries two, and the model carries a config flag, all because the
mapping logic was forced into the validation layer.


#### `_coerce_from_row` is pattern-sniffing

The validator decides whether incoming data needs the row-to-API
rewrite by checking `if isinstance(data, dict) and "first_name" in
data`. That is structural inference, not a type signal. It works
because no current API payload happens to contain a `first_name`
key. The day a future payload does (a registration endpoint that
takes both `first_name` and `full_name`, a webhook that mirrors
some upstream system's field names, anything), the validator
misfires silently. There is no declared input type for the
"row-shaped" branch, so there is no way for a type checker or a
reviewer to catch the collision.


#### `to_row` is asymmetric machinery

The forward direction (row to API) is a `@model_validator`, a
declarative-feeling decorator that integrates with Pydantic's
machinery. The reverse direction (API to row) is a regular method,
because Pydantic has no first-class concept of "convert this model
back to some other type." The two halves of the same mapping live
at completely different levels of abstraction. Worse, `to_row`
takes a keyword-only `password_hash` argument because the API
representation simply does not carry that field. A caller has to
know to pass it; the framework offers no help. Forget it and
Python raises a generic `TypeError` from inside `to_row`'s
signature, far from the mapping logic itself.


#### Bidirectional invariants are unenforced

The id transform is a pair: `f"usr_{db_id:08d}"` going one way and
`int(api_id.removeprefix("usr_"))` going back. They have to stay in
sync. Change the prefix from `usr_` to `user_` in one place without
the other and round-tripping silently breaks: the API now produces
`user_00000001` but `to_row` still calls `removeprefix("usr_")`,
which is a no-op on a string that doesn't start with `usr_`, so the
parse succeeds with the wrong digits. The two halves live in
different methods, in different directions, with no syntactic
connection between them. Nothing in Pydantic flags the drift.


#### The asymmetric `full_name` split is buried in `to_row`

The combining logic (`first_name + last_name -> full_name`) appears
in `_coerce_from_row` near the top of the model. The splitting
logic (`full_name.partition(" ") -> first_name, last_name`) appears
in `to_row` near the bottom. They are two halves of the same
asymmetric transform, but they sit on opposite sides of the model
body with no visual or syntactic pairing. A reader looking at one
half has to scroll, search, and trust convention to find the other.
A change to one half has no mechanism to remind the author about
the other.

----

### With Betwixt: each side does what it does best

The Betwixt version of the same scenario, in full, is the example from
[The two sides](#the-two-sides) plus [Betwixt](#betwixt). To
recap what changes:

- The Pydantic `UserResponse` becomes a clean API model with no
  `model_validator`, no `populate_by_name`, no `validation_alias`,
  no `computed_field`-with-derived-state-from-the-other-type, no
  `to_row` method. It describes the API contract and nothing else.
- The dataclass `UserRow` is unchanged.
- The mapping logic moves out of both types and into `UserBetwixt`,
  where each direction is named, declared, and visually paired with
  its counterpart (or its explicit absence).

The same problem decomposes into three independent components:

| Concern         | Owner                        | What lives there                             |
|-----------------|------------------------------|----------------------------------------------|
| API validation  | Pydantic                     | `UserResponse` model + standard Pydantic     |
| DB persistence  | stdlib dataclass / your ORM  | `UserRow` definition                         |
| The mapping     | Betwixt                      | `UserBetwixt` body                           |

Each component does one thing. None of them knows about the others.
Betwixt is the only piece that needs to know both sides exist; the sides
themselves remain ignorant of each other and of Betwixt.


### What the comparison shows

The claim is narrow and specific: **Pydantic is the right tool for
validation, and the wrong tool for being a mapping layer.** When you
make a Pydantic model carry the mapping responsibility, you get
pressure on the model in directions Pydantic was not designed to
handle, and you end up with the kind of ten-decorator monstrosity
above. Betwixt picks up exactly that load and lets the Pydantic model
go back to being a clean API contract.


### Wins from the separation


#### No model-stuffing

`UserResponse` describes the API contract. That is its whole job.
The body lists fields, types, and any pure API-side validation
rules (a regex on `email`, a length cap on `tags`). FastAPI can
register it as a response model. `model_json_schema()` produces a
clean schema with no row-shaped artifacts. A new team member
reading the file learns what the API returns and nothing else.
The combining logic for `full_name`, the `usr_` prefix on `id`,
the absence of `password_hash` from the wire format: none of that
appears here, because none of it is part of what the API contract
says.


#### No privileged direction

In `UserBetwixt`, `full_name_rightward` and `full_name_leftward`
sit next to each other as sibling class attributes. Both are
declarations. Both use the same construct vocabulary
(`map_rightward` and `map_leftward`). A reviewer reads them as a
pair. The Pydantic-alone version splits the same logic across a
`@model_validator` (declarative-feeling, integrated with the
framework) and a regular method (`to_row`, just a method on a
class). The two halves do not look like the same kind of thing,
because they are not the same kind of thing in Pydantic. Betwixt
flattens that asymmetry: every translation, in every direction,
has the same syntactic weight.


#### Asymmetry is visible

A transform that is genuinely not a clean round-trip should look
that way in the source. `full_name` is the canonical case: forward
combines two strings with a space; backward splits on the first
space and hopes for the best. Those two operations are not
inverses, and treating them as if they were would be a bug.
Betwixt names each direction explicitly (`full_name_rightward`,
`full_name_leftward`), so a reviewer scanning the body sees both
halves in the same visual neighborhood and recognizes the
asymmetry on sight. The Pydantic-alone version hides one half in
a `model_validator` and the other in a method, possibly across
file boundaries. The asymmetry is still there; the reviewer just
has to assemble it from clues.


#### Required explicit pairing

A bidirectional transform has two halves, and both have to be
written. Betwixt will not synthesize the inverse of
`f"usr_{db_id:08d}"` for you, even though the inverse looks
obvious. That sounds like make-work, but it kills an entire class
of silent failures. Change the prefix from `usr_` to `user_` in
one half and a code review (or a test) catches that the other
half no longer matches. Compare the Pydantic-alone version, where
the two halves live in different methods on the same model: a
prefix change in `_coerce_from_row` that the author forgets to
mirror in `to_row` produces a model that round-trips wrong, with
no warning at any layer. Explicit pairing is annoying exactly
once per transform, and pays back every time the transform
changes.


#### Required defaults

The API has no `password_hash` field, but the database does. When
translation goes API to DB, that field has to come from
somewhere. Betwixt forces the answer at definition time:

```python
password_hash_leftward = default_leftward(
    left=L.password_hash,
    default=lambda ctx: ctx["new_password_hash"],
)
```

The construct names the field, names the source (caller-supplied
context), and lives in the Betwixt model body where every other
translation rule lives. The Pydantic-alone version pushes the
problem to the call site: `to_row(password_hash=...)` is a
keyword-only argument that callers either remember or trip over
at runtime. There is no declaration to scan, no inventory to
audit, and no framework-level signal that says "this field is
fundamental to the leftward direction." Betwixt makes it a
declaration; Pydantic-alone makes it a TypeError waiting for a
distracted caller.


#### Both types stay clean

The Pydantic `UserResponse` has no `populate_by_name`, no
`validation_alias`, no `serialization_alias`, no `model_validator`
that pattern-sniffs incoming dicts, no `to_row` method, no
keyword-only arguments to remember. The dataclass `UserRow` has
no metadata, no helper methods, no awareness that an API exists.
Either type can be lifted out of the project and used somewhere
else without dragging mapping logic along. Two teams can own them
independently: the API team owns `UserResponse`, the database
team owns `UserRow`, and the integration team owns `UserBetwixt`.
Changes to one type do not require negotiation with the other.

---

### Honest costs of the separation

The separation is not free. Three costs are worth naming honestly,
along with the bounds on each.


#### One more concept to learn

A reader new to the codebase has to grasp what a betwixt is, what
the construct vocabulary means, and where the translation logic
lives. The Pydantic-alone version is more surface area in one
place but conceptually one library: if the reader knows Pydantic,
they can puzzle through the model. The Betwixt version is two
libraries collaborating, which is a higher conceptual ceiling
even though each library does less. The tradeoff makes sense
once a project has more than one or two row-to-API mappings;
for a single small mapping, Pydantic alone is genuinely simpler.


#### Two declarations for asymmetric cases

`full_name_rightward` plus `full_name_leftward` is two class
attributes for what the Pydantic-alone version expresses as a
single model field. The verbosity is the point: the two
directions are not the same operation, and writing them as
separate declarations forces the asymmetry into view. But "the
verbosity is the point" is still verbosity, and a reviewer
looking at a long betwixt body for the first time will count
attributes and notice. The verbosity scales linearly with the
number of asymmetric fields, not with the number of fields
overall (1:1 fields need no declaration), so this cost is
bounded by how much genuine asymmetry your two sides carry.


#### No magic inversion

Even when a transform is genuinely invertible
(`f"usr_{x:08d}"` paired with `int(api_id.removeprefix("usr_"))`),
Betwixt requires both halves. The library will not generate the
inverse for you, and `map_pairwise` is just a syntactic grouping
of two independent functions, not an inversion check. This is a
deliberate tradeoff: explicitness over cleverness. A library
that auto-inverts simple transforms would handle the obvious
cases for free, but the rules for what counts as "obvious" leak
complexity (does it invert lambdas? regex substitutions? user
functions?), and the moment a reader cannot tell whether a given
transform was inverted automatically or manually, the
declarative clarity is gone. Betwixt picks the boring path: every
direction you want, you write.

----

## Case studies

Three worked examples, each picked to exercise a different facet of
the design.

1. **User** -- the running example built up across the spec body.
   Exercises the basic taxonomy: name renames, derived fields,
   asymmetric splits, defaults, and one-side-only fields.
2. **Payment** -- a multi-currency payments service. Exercises
   runtime context, multi-field input on both sides, and genuinely
   rightward-only fields.
3. **Order** -- a shopping order with line items, a customer, and
   an optional shipping address. Exercises nesting in all its
   shapes: 1:1 nested, list-nested, optional-nested, plus context
   propagation through nested betwixts.

The three together exercise every construct in the taxonomy at
least once, in patterns drawn from real applications rather than
contrived to hit a checkbox.


### User: the basic taxonomy (recap)

`UserBetwixt` is the running example developed across the spec
body. It pairs a stdlib `@dataclass` (`UserRow`) with a Pydantic
`BaseModel` (`UserResponse`) and shows the basic constructs in
isolation: `map_pairwise` for shared fields with light transforms
(`id`'s prefix), `map_rightward` and `map_leftward` for
asymmetric splits (`full_name` ↔ `first_name`/`last_name`),
`reduce_rightward` for a derived field that needs runtime context
(`is_recent`), `default_leftward` for an inverse-direction-only
default (`password_hash`), and the implicit-1:1 rule for
same-name fields (`tags`, `created_at`).

Refer back to [The two sides](#the-two-sides), [Betwixt](#betwixt),
and [Using Betwixt](#using-betwixt) for the full development. The
remaining two case studies build on what `UserBetwixt` establishes
without re-deriving it.


### Payment: runtime context, asymmetric directions, multi-field inputs

The User example does not exercise three things that show up
constantly in real applications:

1. **Lossy transforms that need external context.** A value can
   only be translated correctly if some piece of information that
   lives on *neither* side is supplied at translation time (an FX
   rate, a request user, a feature flag).
2. **Field semantics that depend on the value of another field.**
   "1099" means $10.99 if the currency is USD but means ¥1099 if
   the currency is JPY. Logic must branch on data, not just on
   type.
3. **Genuinely asymmetric directionality.** Sometimes the
   rightward transform is well-defined and the leftward transform
   is meaningless or dangerous to attempt.

A multi-currency payment is a clean way to surface all three.


#### The scenario

A payments service stores transactions in their **native
currency** in the database. A US-facing frontend wants every
transaction normalized to USD for display, with the original
currency shown alongside as context. FX rates are supplied at
request time by an upstream service; they are not part of either
persistence or API state.


#### The two sides

```python
from dataclasses import dataclass
from decimal import Decimal
from pydantic import BaseModel
import pendulum


@dataclass
class PaymentRow:
    """As stored in the database."""
    id: int
    amount_minor: int # 1099 means 10.99 only in currencies with 2 minor units
    currency: str     # ISO 4217: "USD", "EUR", "JPY", ...
    occurred_at: pendulum.DateTime


class PaymentResponse(BaseModel):
    """As returned to the US-facing frontend."""
    id: str                    # "pay_00001099"
    amount_usd: Decimal        # always USD, rounded to 2 decimal places
    original_amount: Decimal   # the native amount, scaled to "major" units
    original_currency: str
    fx_rate_used: Decimal      # the rate that produced amount_usd; for
                               # client-side audit and reconciliation
    occurred_at: pendulum.DateTime
```

Two helper facts the Betwixt model needs to express:

```python
# How many minor units make one major unit, per currency.
# JPY, KRW, etc. have zero minor units; most others have two.
MINOR_UNITS = {"JPY": 0, "KRW": 0, "USD": 2, "EUR": 2, "GBP": 2}

def to_major(minor: int, currency: str) -> Decimal:
    """
    Convert to major denomination.

    Example:
        (1099, 'USD') -> Decimal('10.99')
        (1099, 'JPY') -> Decimal('1099')
    """
    places = MINOR_UNITS.get(currency, 2)
    return Decimal(minor) / (Decimal(10) ** places)


def to_minor(major: Decimal, currency: str) -> int:
    """Inverse of to_major. Truncates to the currency's minor unit precision."""
    places = MINOR_UNITS.get(currency, 2)
    return int((major * (Decimal(10) ** places)).quantize(Decimal("1")))
```

Note that **neither side knows about FX rates.** The DB doesn't
store them (rates change constantly; storing the rate at write
time would be wrong for queries that ask "what's this worth
now?"). The API exposes `fx_rate_used` purely as audit metadata;
it is computed *during* translation, not stored on either end.


#### A first attempt at the Betwixt model (and why it fails)

The natural first sketch:

```python
from betwixt import Betwixt, f, map_pairwise, map_rightward, default_leftward


class PaymentBetwixt(Betwixt):
    left = PaymentRow
    right = PaymentResponse
    L, R = f(left), f(right)

    id = map_pairwise(
        left=L.id,
        right=R.id,
        rightward=lambda i: f"pay_{i:08d}",
        leftward=lambda s: int(s.removeprefix("pay_")),
    )

    # PROBLEM: how does the rightward function get the FX rate?
    amount_usd = map_rightward(
        left=(L.amount_minor, L.currency),
        right=R.amount_usd,
        rightward=lambda minor, ccy: ???,  # needs fx_rate from somewhere
    )
```

This sketch reveals the real design hole. The rightward function
for `amount_usd` needs three things:

- `L.amount_minor` (lives on the left side)
- `L.currency` (lives on the left side)
- The current USD-per-`L.currency` FX rate (lives **nowhere** on either side)

The first two are field references. The third is what [Runtime
context](#runtime-context) is for: a translation function
declares a final `ctx` parameter and the caller supplies a
matching `context=` dict at translate time.

```python
amount_usd = map_rightward(
    left=(L.amount_minor, L.currency),
    right=R.amount_usd,
    rightward=lambda minor, ccy, ctx: (
        (to_major(minor, ccy) * ctx["fx_rates"][ccy]).quantize(Decimal("0.01"))
    ),
)
```

The caller invokes:

```python
PaymentBetwixt.rightward(
    row,
    context={"fx_rates": {"EUR": Decimal("1.08"), "JPY": Decimal("0.0067")}},
)
```


#### The full Betwixt model

```python
from betwixt import (
    Betwixt, f,
    map_pairwise, map_rightward, project_rightward, default_leftward,
)


class PaymentBetwixt(Betwixt):
    left = PaymentRow
    right = PaymentResponse
    L, R = f(left), f(right)

    # id, occurred_at: the implicit-1:1 rule handles occurred_at;
    # id needs the prefix transform.
    id = map_pairwise(
        left=L.id,
        right=R.id,
        rightward=lambda i: f"pay_{i:08d}",
        leftward=lambda s: int(s.removeprefix("pay_")),
    )

    # The native amount, displayed in major units, paired with currency.
    # Pure data reshape, no FX involved.
    original_amount_rightward = map_rightward(
        left=(L.amount_minor, L.currency),
        right=R.original_amount,
        rightward=to_major,
    )
    original_currency_rightward = map_rightward(
        left=L.currency,
        right=R.original_currency,
        rightward=lambda c: c,
    )

    # USD-normalized amount. Needs the FX rate context.
    amount_usd_rightward = map_rightward(
        left=(L.amount_minor, L.currency),
        right=R.amount_usd,
        rightward=lambda minor, ccy, ctx: (
            to_major(minor, ccy) * ctx["fx_rates"][ccy]
        ).quantize(Decimal("0.01")),
    )

    # The rate itself becomes part of the response, for audit.
    fx_rate_used_rightward = map_rightward(
        left=L.currency,
        right=R.fx_rate_used,
        rightward=lambda ccy, ctx: ctx["fx_rates"][ccy],
    )

    # Leftward: the API gives us original_amount + original_currency,
    # which together reconstruct amount_minor exactly. amount_usd and
    # fx_rate_used are derived, so leftward ignores them entirely.
    amount_minor_leftward = map_leftward(
        right=(R.original_amount, R.original_currency),
        left=L.amount_minor,
        leftward=to_minor,
    )
    currency_leftward = map_leftward(
        right=R.original_currency,
        left=L.currency,
        leftward=lambda c: c,
    )
```

----

### Order: nesting in all its shapes

The Payment example exercises field-level constructs. A real
application also has *structural* nesting: a top-level type whose
fields are themselves structured types that have their own
betwixts. The User and Payment examples have flat schemas; this
case study deliberately picks a domain where every interesting
shape of nesting shows up at once.

A shopping order has:

- A **customer** (single nested object).
- A **list of line items** (list-nested).
- An **optional shipping address** (some orders are digital with
  no shipping).
- Order-level totals derived rightward from the items and the
  current FX rates.

Each inner type translates between a DB representation and an API
representation in its own right, so each gets its own `Betwixt`
subclass. The outer `OrderBetwixt` composes them via `nested_*`
constructs and threads context through where needed.


#### The scenario

The order service stores native-currency line items (same
representation as Payment: minor units plus currency code). The
API exposes USD-normalized prices, an item count, and addresses
enriched with geocoded coordinates for map display. Three runtime
services contribute context:

- An **FX-rate snapshot** (same shape as Payment).
- A **geocoder** that resolves a street address to a `(lat, lon)`.
- A **tax-region resolver** that maps a country code to a
  jurisdiction string.

Each of those services is consumed by exactly one inner betwixt,
and the outer `OrderBetwixt` declares which slice of the call-time
context each inner receives.


#### The two sides

```python
from dataclasses import dataclass
from decimal import Decimal
from pydantic import BaseModel
import pendulum


# --- Left side: DB-shaped dataclasses ---

@dataclass
class CustomerRow:
    id: int
    full_name: str
    email_address: str
    country: str  # used to derive tax_region rightward

@dataclass
class AddressRow:
    id: int
    street: str
    city: str
    country: str

@dataclass
class LineItemRow:
    id: int
    sku: str
    quantity: int
    unit_price_minor: int
    currency: str

@dataclass
class OrderRow:
    id: int
    customer: CustomerRow
    items: list[LineItemRow]
    shipping_address: AddressRow | None
    currency: str  # the order's settlement currency, same as items'
    created_at: pendulum.DateTime


# --- Right side: API-shaped Pydantic models ---

class CustomerResponse(BaseModel):
    id: str
    full_name: str
    email: str
    tax_region: str             # derived rightward via tax_regions service

class AddressResponse(BaseModel):
    id: str
    street: str
    city: str
    country: str
    lat: float                  # derived rightward via geocoder
    lon: float                  # derived rightward via geocoder

class LineItemResponse(BaseModel):
    id: str
    sku: str
    quantity: int
    unit_price_usd: Decimal     # derived rightward via fx_rates
    line_total_usd: Decimal     # quantity * unit_price_usd

class OrderResponse(BaseModel):
    id: str
    customer: CustomerResponse
    items: list[LineItemResponse]
    shipping_address: AddressResponse | None
    subtotal_usd: Decimal       # derived rightward from items + fx_rates
    item_count: int             # derived rightward from items
    created_at: pendulum.DateTime
```

The `id` prefix convention from Payment carries over: rightward
adds a domain-specific prefix (`"cus_"`, `"adr_"`, `"itm_"`,
`"ord_"`), leftward strips it. To save space, the inner betwixts
below use a small helper:

```python
def make_id_pair(prefix: str) -> tuple[Callable, Callable]:
    return (
        lambda i: f"{prefix}{i:08d}",
        lambda s: int(s.removeprefix(prefix)),
    )
```


#### The inner Betwixt models

##### `CustomerBetwixt`

Renames `email_address` to `email`. Derives `tax_region` from
`country` using a service supplied at translation time. `country`
is rightward-only consumed by the derivation; the API response
does not expose it as a separate field, so there is no leftward
construct for it.

```python
class CustomerBetwixt(Betwixt):
    left = CustomerRow
    right = CustomerResponse
    L, R = f(left), f(right)

    _id_right, _id_left = make_id_pair("cus_")
    id = map_pairwise(left=L.id, right=R.id, rightward=_id_right, leftward=_id_left)

    email = map_pairwise(
        left=L.email_address,
        right=R.email,
        rightward=lambda e: e,
        leftward=lambda e: e,
    )

    tax_region_rightward = map_rightward(
        left=L.country,
        right=R.tax_region,
        rightward=lambda country, ctx: ctx["tax_regions"].lookup(country),
    )
    # full_name: implicit 1:1
```

##### `AddressBetwixt`

Geocodes the street/city/country into `(lat, lon)` rightward; the
leftward direction throws away the coordinates and reconstructs
the row from the textual fields. This is the
rightward-only-context pattern in pure form.

```python
class AddressBetwixt(Betwixt):
    left = AddressRow
    right = AddressResponse
    L, R = f(left), f(right)

    _id_right, _id_left = make_id_pair("adr_")
    id = map_pairwise(left=L.id, right=R.id, rightward=_id_right, leftward=_id_left)

    coords_rightward = reduce_rightward(
        right=(R.lat, R.lon),
        rightward=lambda row, ctx: ctx["geocoder"].lookup(
            row.street, row.city, row.country,
        ),
    )
    # street, city, country: implicit 1:1
```

##### `LineItemBetwixt`

Same currency-conversion pattern as Payment, but per line item.
Computes `unit_price_usd` and `line_total_usd` rightward;
reconstructs `unit_price_minor` and `currency` leftward from the
response fields.

```python
class LineItemBetwixt(Betwixt):
    left = LineItemRow
    right = LineItemResponse
    L, R = f(left), f(right)

    _id_right, _id_left = make_id_pair("itm_")
    id = map_pairwise(left=L.id, right=R.id, rightward=_id_right, leftward=_id_left)

    unit_price_usd_rightward = map_rightward(
        left=(L.unit_price_minor, L.currency),
        right=R.unit_price_usd,
        rightward=lambda minor, ccy, ctx: (
            to_major(minor, ccy) * ctx["fx_rates"][ccy]
        ).quantize(Decimal("0.01")),
    )

    line_total_usd_rightward = reduce_rightward(
        right=R.line_total_usd,
        rightward=lambda row, ctx: (
            to_major(row.unit_price_minor, row.currency)
            * ctx["fx_rates"][row.currency]
            * row.quantity
        ).quantize(Decimal("0.01")),
    )

    # Leftward: the response's unit_price_usd round-trips through
    # the order's settlement currency. The order itself supplies
    # the currency context leftward (see OrderBetwixt), so the
    # inner needs ctx["settlement_currency"] on leftward calls.
    unit_price_minor_leftward = map_leftward(
        right=R.unit_price_usd,
        left=L.unit_price_minor,
        leftward=lambda usd, ctx: to_minor(usd, ctx["settlement_currency"]),
    )
    currency_leftward = default_leftward(
        left=L.currency,
        default=lambda ctx: ctx["settlement_currency"],
    )
    # sku, quantity: implicit 1:1
```

----

#### The outer Betwixt model

```python
class OrderBetwixt(Betwixt):
    left = OrderRow
    right = OrderResponse
    L, R = f(left), f(right)

    _id_right, _id_left = make_id_pair("ord_")
    id = map_pairwise(left=L.id, right=R.id, rightward=_id_right, leftward=_id_left)

    # 1:1 nested. Customer needs the tax_regions service rightward;
    # leftward needs nothing (omit context_leftward; inner gets None).
    customer = nested_pairwise(
        left=L.customer,
        right=R.customer,
        via=CustomerBetwixt,
        context_rightward=lambda ctx: {"tax_regions": ctx["tax_regions"]},
    )

    # Optional nested. shipping_address may be None on either side.
    # Address needs the geocoder rightward; leftward needs nothing.
    shipping_address = nested_pairwise(
        left=L.shipping_address,
        right=R.shipping_address,
        via=AddressBetwixt,
        context_rightward=lambda ctx: {"geocoder": ctx["geocoder"]},
    )

    # List nested. Each LineItem needs fx_rates rightward and
    # settlement_currency leftward (so it can reconstruct minor units).
    items = nested_pairwise(
        left=L.items,
        right=R.items,
        via=LineItemBetwixt,
        context_rightward=lambda ctx: {"fx_rates": ctx["fx_rates"]},
        context_leftward=lambda ctx: {"settlement_currency": ctx["settlement_currency"]},
    )

    # Order-level totals derived rightward from the outer's left side.
    # These are non-nested constructs that coexist with the nested ones.
    subtotal_usd_rightward = reduce_rightward(
        right=R.subtotal_usd,
        rightward=lambda row, ctx: sum(
            (
                to_major(item.unit_price_minor, item.currency)
                * ctx["fx_rates"][item.currency]
                * item.quantity
                for item in row.items
            ),
            start=Decimal("0"),
        ).quantize(Decimal("0.01")),
    )

    item_count_rightward = reduce_rightward(
        right=R.item_count,
        rightward=lambda row: len(row.items),
    )
    # currency, created_at: implicit 1:1 / leftward-only flow
```

The caller invokes:

```python
response = OrderBetwixt.rightward(
    order_row,
    context={
        "fx_rates": {"EUR": Decimal("1.08"), "JPY": Decimal("0.0067"), "USD": Decimal("1")},
        "geocoder": geocoder_service,
        "tax_regions": tax_regions_service,
    },
)

# Round-trip the response back to a row (for, say, applying a
# patch from a PUT endpoint). The leftward direction needs to know
# what currency to denominate the line items in, since the API
# only carries USD; the order's own `currency` field supplies it.
row_again = OrderBetwixt.leftward(
    response,
    context={"settlement_currency": response_for_order.currency},
)
```

Reading `OrderBetwixt`'s body gives a complete inventory of the
context keys this call needs. Three keys for rightward (`fx_rates`,
`geocoder`, `tax_regions`), one for leftward (`settlement_currency`).
Each is declared at the line that consumes it (or forwards it to
an inner). No spelunking into `CustomerBetwixt`, `AddressBetwixt`,
or `LineItemBetwixt` is required to know what to pass at the call
site -- the outer's `context_*=` declarations are the binding
contract.

----

### What these exercise

Across the three case studies, the taxonomy gets a workout that
covers every construct at least once and most constructs in
multiple shapes.


#### Construct coverage

| Construct            | User                   | Payment                                   | Order                                    |
|----------------------|------------------------|-------------------------------------------|------------------------------------------|
| `map_pairwise`       | id                     | id                                        | every nested betwixt's id                |
| `map_rightward`      | full_name split        | original_amount, amount_usd, fx_rate_used | tax_region, unit_price_usd               |
| `map_leftward`       | full_name → first/last | amount_minor, currency                    | unit_price_minor                         |
| `reduce_rightward`   | is_recent              | --                                        | line_total_usd, subtotal_usd, item_count |
| `default_leftward`   | password_hash          | --                                        | currency (line item)                     |
| `nested_pairwise`    | --                     | --                                        | customer, shipping_address, items        |
| `context_rightward=` | --                     | --                                        | all three nested constructs              |
| `context_leftward=`  | --                     | --                                        | items (settlement_currency)              |
| `context_pairwise=`  | --                     | --                                        | --                                       |
| `project_*`          | --                     | --                                        | --                                       |

The `project_*` constructs do not appear in the case studies.
They exist for the cases where the entire object on one side has
to be built in one shot from the entire object on the other --
typically when a single source object materializes into a
target whose construction logic does not factor cleanly per
field. None of the three case studies has that shape, which is
fair: `project_*` is the escape hatch, not the common case. The
spec body documents it; a real fourth case study (a
heavily-denormalized join across three DB tables flattened into
one API resource, say) would exercise it.

`context_pairwise=` also goes unused, for a different reason:
Order's nested constructs need different keys in each direction
(`fx_rates` rightward, `settlement_currency` leftward), so the
directional split is the natural fit. `context_pairwise=` is the
shortcut for nested constructs whose inner needs the same context
shape in both directions, which none of these three case studies
happens to have.


#### Pattern coverage

##### Same-name 1:1 fields handled implicitly

All three case studies rely on the implicit-1:1 rule for fields
that don't need a transform (`tags`, `created_at`, `street`,
`city`, `country`, `sku`, `quantity`, ...). The taxonomy
explicitly covers the case where no declaration is the right
declaration.


##### Asymmetric splits

User's `full_name` ↔ `first_name`/`last_name`, Payment's
`amount_minor` ↔ `original_amount`/`original_currency`, and
Order's `unit_price_usd` ↔ `unit_price_minor` (with currency from
context) all use the multi-field-input pattern. The function
signature mirrors the tuple order in `left=` / `right=`.


##### Rightward-only fields

Payment's `amount_usd` and `fx_rate_used`, all of Address's
`lat`/`lon`, Customer's `tax_region`, and the order-level totals
all have no leftward counterpart. The engine treats fields with
no contributor in a given direction as "not produced in that
direction"; no special construct is needed.


##### Nested in all three shapes

Order exercises 1:1 nested (`customer`), optional nested
(`shipping_address`), and list-nested (`items`) in one outer
betwixt. Container traversal is handled by the framework via
`typing.get_origin()` / `get_args()`; the user writes the same
`nested_pairwise(...)` declaration regardless of container shape.


##### Context propagation through nested betwixts

Order's outer declares per-construct `context_rightward=` and
`context_leftward=` callables that slice the caller's context
dict for each inner. The outer caller passes one big context
dict; the outer betwixt's body is a complete inventory of the
keys consumed transitively.


##### Asymmetric per-direction context

Customer and Address only need rightward context (the geocoder,
the tax-region service); their leftward direction is plain
structural translation. The outer omits `context_leftward=` for
those nested constructs and the inners receive `context=None` on
leftward calls -- the loud-failure default.


#### Verbosity and reading experience

The Payment betwixt body is 11 declarations plus three
module-level helpers. The Order outer betwixt is 7 declarations;
the three inner betwixts add 12 more between them, for 19 total.
Compare this to the hand-rolled equivalents (a
`PaymentResponse.from_row(row, fx_rates)` classmethod plus a
`to_row()`; an `OrderResponse.from_row(row, services)` that walks
each nested object inline; corresponding `to_row()` methods for
both): the line counts come out roughly comparable, but the
hand-rolled versions bundle every translation into two unsorted
methods per type. The Betwixt versions name every translation,
pair related ones via the `_rightward`/`_leftward` suffix
convention, and make every external dependency visible at the
line where it is consumed.

The taxonomy holds up across all three case studies. Working
through them did not surface a missing construct or a needed API
change. The case studies fed nothing back that the design could
not absorb.

---

## The case for Betwixt

Betwixt is a *relationship spec* between two structured types,
with directionality as a first-class concern, sitting on top of
whatever type-modeling libraries each side already uses.

The strongest argument for building it:

> The entire Python validation/serialization ecosystem -- Pydantic,
> attrs, msgspec, dataclasses, marshmallow, cattrs -- assumes data
> flows between one in-memory type and one wire format. None of
> them treat the case where two distinct in-memory types need to
> map to each other as a first-class problem.

Pydantic models are one type with a `model_dump` escape hatch.
Marshmallow schemas are one-way. Cattrs has structure/unstructure
but both ends point at the same canonical form. When real
applications need to map between a DB type and an API type (the
most common case in any non-trivial backend), users either reach
for Pydantic and stuff the mapping logic into the model, or they
hand-roll a `to_x`/`from_x` method pair with no framework
support. Betwixt names exactly the gap nobody else fills.

What this design buys, concretely:

**Both sides stay clean.** Pydantic models remain pure API
contracts. Dataclasses (or ORM rows, or attrs classes) remain
pure persistence types. Neither side knows the other exists;
neither knows Betwixt exists.

**Directionality is visible.** `leftward` and `rightward` are
siblings in the Betwixt model body. A reviewer reads asymmetric
transforms as paired declarations, not as a
model-validator-plus-method combination spread across two parts
of a file.

**Runtime dependencies are visible.** Translations that need
per-call values (an FX rate, the current time, the requesting
user) accept a `ctx` parameter and reach into the caller-supplied
context dict by name (`ctx["fx_rates"]`, `ctx["now"]`). The
framework inspects the function signature once, at
construct-definition time, and only routes context to functions
that opted in. Functions that don't need context never see it.

**The library does one thing.** Mapping. Not validation, not
serialization, not schema generation, not codecs. Each existing
library keeps doing what it does best; Betwixt fills the seam
between them.


## Risks

The biggest risk is that the asymmetric-transform syntax (paired
`map_rightward` / `map_leftward` declarations sharing a name
stem) does not stay clean as real codebases pile cases onto it.
The three [case studies](#case-studies) cover the shapes the spec
was designed against -- field-level transforms, runtime context,
asymmetric directions, and nesting -- and read cleanly. Whether
that holds at 30 fields per side, or with five layers of nesting,
or under heavy `project_*` use, is unproven.

The taxonomy bet is that twelve constructs is enough vocabulary
to cover the realistic shapes without forcing escape hatches.
That bet survives the case studies but has not been tested at
scale. The escape hatch (`project_*`) exists precisely so the
taxonomy doesn't have to be exhaustive, but heavy `project_*` use
in a real codebase would be the signal that the per-field
constructs are missing something.

The third risk is scope creep. Betwixt's case rests on doing one
job and staying out of the validation and serialization
business. The moment Betwixt starts growing JSON codecs or
schema generators, it becomes another half-validation-library
competing on Pydantic's home turf, and the seam-filling argument
collapses. The discipline has to hold not just at v0.1 but
across every "wouldn't it be nice if Betwixt could also..."
issue that follows.


## Future validation

Two more case studies are worth working through before any code
is written:

- A heavily-denormalized join across three DB tables to one API
  resource. This would exercise `project_*`, the only construct
  the existing case studies don't, and would test whether the
  whole-object construction path reads as cleanly as the
  per-field path.
- A polymorphic union with a discriminator field. The spec punts
  this to `map_*` with type dispatch; whether that holds up in
  practice (versus, say, demanding a first-class `union_*`
  construct) is the open question.

If those examples produce betwixt bodies that need escape hatches
beyond `project_*`, or read worse than the hand-rolled
equivalent, the taxonomy needs another pass before any code is
written.


## When not to use Betwixt

Betwixt only earns its keep when both sides of a mapping are
non-trivial types that exist for independent reasons (a DB row
that exists because of the schema, an API model that exists
because of the contract). For codebases where one side is "just
a dict" or where the API model is genuinely the same shape as
the DB row, Betwixt is overkill and a plain Pydantic model is
the right answer.

The library should be honest about this in its docs:

> If you don't already have two types, you don't need Betwixt.


## Conclusion

Betwixt fills a real gap in the Python type-modeling ecosystem:
the seam between two in-memory types that both exist for good
independent reasons. The design keeps both sides clean, makes
directionality and runtime dependencies visible at the
declaration site, and resists the gravitational pull toward
becoming yet another validation library.

The case studies show the taxonomy holds up across the shapes it
was designed against. The risks are honest and bounded: the
syntax may not scale to extreme cases, and the library is wrong
for codebases that don't already have two types. Both of those
are knowable from the docs, and neither sinks the design.

Worth building.
