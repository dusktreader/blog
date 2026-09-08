---
date: 2026-09-08
authors:
  - the.dusktreader
comments: true
tags:
  - Python
  - Pydantic
  - SQLAlchemy
  - dataclasses
  - PyPI
categories:
  - dev-tools
---

# Introducing Betwixt: a declarative data transformation layer

[![betwixt-logo](https://dusktreader.github.io/betwixt/static/logo.png)](https://github.com/dusktreader/betixt){target="blank", width=600}

!!! tip "TLDR"
    The first full-featured release of [`betwixt-data`](https://pypi.org/project/betwixt-data/) is now on PyPI. Betwixt
    gives the translation between your API, application, and database models a first-class home without making those
    models depend on one another.

In my years building Python APIs, I've found that I'm describing the same entity across more than one data model. The
API endpoints usually have a Pydantic model tailored for RESTful calls while the database has a different representation
of the same entity in a SQLAlchemy ORM model. Then, you might even have a mixed bag of external service representations,
logging representations, and sometimes event schemas that embed the same entity.

The differences between the data types are important for the _way_ that format of the data is used. Some examples might
include:

* The API exposes a display name while the database stores first and last names
* The API uses camelCase while the database uses snake_case
* The API represents money in dollars while the database uses cents
* The API nests line items while the database stores normalized rows
* The API computes totals from request-time currency context
* A partial update contains one changed field while the complete database model requires several

Translating between those shapes, however, always gets a bit messy. You find yourself using Pydantic aliases and
validators mixed with SQLAlchemy model properties. Then, you might add in other helper methods and even explicit
field-by-field translation functions. When you need to add fields or change types, you have to remember all the
different places where the hodge-podge of models and translation methods need to be updated.

Betwixt provides a single simple declarative method for defining the complete translation between two data types in
both directions and a simple way to execute the translation. The models remain ordinary models. Betwixt does not
replace Pydantic, SQLAlchemy, dataclasses, or any other data type; it connects them.


<!-- more -->


## The problem at the boundary

Let's start with a simple example. Imagine an account that crosses an API and database boundary. The database stores
these fields in a SQLAlchemy ORM model:

```python
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AccountRow(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column("given_name", String(100))
    last_name: Mapped[str] = mapped_column("family_name", String(100))
    email_address: Mapped[str] = mapped_column(String(255))
    balance_cents: Mapped[int] = mapped_column(Integer)
```

The API exposes a different contract through a Pydantic model:

```python
from pydantic import BaseModel, ConfigDict, Field


class AccountView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    display_name: str = Field(alias="displayName")
    email: str = Field(alias="emailAddress")
    balance_dollars: float = Field(
        alias="balanceDollars",
        ge=0,
    )
```

The two types describe the same account, but they are not interchangeable. A serializer is not enough because the
translation is not just a change of wire format:

- `first_name` and `last_name` combine into `display_name` in one direction.
- `display_name` must split back into two fields in the other direction.
- `email_address` and `email` are the same value with different names.
- `balance_cents` and `balance_dollars` need different conversion functions.

You can implement this with model methods and endpoint code. It works. As the surface area of either the API or data
boundary grows, however, finding the complete relationship becomes a small archaeological expedition.


## Put the relationship in one place

Betwixt keeps the models focused on their own jobs and places the conversion rules in a `Betwixt` subclass. The Pydantic
model is the left side, and the SQLAlchemy ORM model is the right side:

```python
from betwixt import Betwixt, expand_rightward, field_refs, map_pairwise


class AccountTwixt(Betwixt):
    left = AccountView
    right = AccountRow
    (L, R) = field_refs(left, right)

    name_parts = expand_rightward(
        left=L.display_name,
        right=(R.first_name, R.last_name),
        rightward=lambda name: tuple((name.split(" ", 1) + [""])[:2]),
    )
    email = map_pairwise(
        left=L.email,
        right=R.email_address,
        rightward=lambda address: address.lower(),
        leftward=lambda address: address,
    )
    balance = map_pairwise(
        left=L.balance_dollars,
        right=R.balance_cents,
        rightward=lambda dollars: round(dollars * 100),
        leftward=lambda cents: cents / 100,
    )
```

The declaration makes the asymmetry visible. `expand_rightward()` splits one left-side field into two right-side fields.
`map_pairwise()` records separate functions for the two directions instead of pretending that Betwixt can infer an
inverse.

All of the translation logic is gathered into one declarative representation that isn't concerned with API aliases,
validation rules, ORM properties, or persistence logic.

Then, converting the Pydantic model on the left into the SQLAlchemy ORM model on the right is done with a _single_
function
call:

```python
mapping = AccountTwixt()

account_view = AccountView.model_validate(
    {
        "id": 42,
        "displayName": "Ada Lovelace",
        "emailAddress": "ada@example.com",
        "balanceDollars": 123.45,
    }
)
account_row = mapping.rightward(account_view)
```

!!! warning "Install the adapter extras"
    Install the `pydantic` and `sqlalchemy` extras to use these adapters. Support is included in Betwixt, but the
    dependencies are not installed without including the extras. See the [Betwixt installation
    documentation](https://dusktreader.github.io/betwixt/quickstart/#installation) for the available installation
    options.


## A mapping is not a serializer

Betwixt has a deliberately narrow job: translate an instance of one structured type into an instance of another. It does
not validate input, parse JSON, serialize output, manage database sessions, or generate schemas.

That gives each tool a clean boundary:

```python
request = AccountView.model_validate(payload)  # Pydantic validates, if this is a Pydantic model
row = AccountTwixt().rightward(request)        # Betwixt translates
session.add(row)                               # SQLAlchemy persists
```

The same separation works in the other direction. Load a database object through your normal persistence layer, pass it
to `leftward()`, and serialize the returned API model with the machinery that already owns that concern.


## Supported mapping shapes

The common case is a field-to-field map, but real boundaries need more than renames and scalar conversions. Betwixt
supports declarations for:

- **Pairwise maps**: transform a field in either direction with independent functions declared for each direction.
- **Directional maps**: define a transformation only when data moves rightward or leftward.
- **Expansions**: split one source field into several destination fields.
- **Reductions**: derive one field from the complete source object.
- **Projections**: build the complete destination object from the source object in one function.
- **Nested mappings**: reuse another Betwixt mapping for nested values and supported containers.
- **Partial translations**: translate sparse dictionaries for patch-like operations without applying defaults.


## Automatic field translation

**Same-name fields with compatible annotations map automatically**. If implicit mapping is too permissive for a
boundary, disable it on the whole `Betwixt` class:

```python
class ExplicitPersonTwixt(Betwixt):
    left = Person
    right = PersonView
    (L, R) = field_refs(left, right)
    disable_implicit_mapping = True

    name = map_pairwise(left=L.name, right=R.name, rightward=str.title, leftward=str.title)
```

To disable implicit mapping in a narrower way, you can use `disable_implicit_pairwise`, `disable_implicit_rightward`, or
`disable_implicit_leftward` with the relevant field references. The directional controls let you choose exactly which
trip needs an explicit rule. This is useful when most same-name fields are fine as-is, but one field needs special
treatment at one boundary.


## Order matters

The order of declarations in the class body matters whenever two rules write to the same destination field. Betwixt
applies the rules as they are declared from top to bottom. So a rule declared later can replace the value produced by an
earlier one. This is useful when you want a general rule first and a more specific rule afterward. It also means that
moving a declaration can change the result, so keep overlapping rules together and order them from broadest to most
specific. If nothing overlaps, declaration order does not change the outcome.


## Mapping context

Mappings can also receive per-call context. This is needed for translations that needs external information that is
only available at runtime. This might include things like currency policies, feature flags, or environment variables.

In such cases, you pass a keyword `ctx` parameter to the `rightward()` or `leftward()` function. The field
translation function that needs the context _must_ receive a keyword-only argument named `ctx`. If such a paramter is
not defined on the translation function, the context will be ignored.

```python
class PaymentTwixt(Betwixt):
    left = Payment
    right = PaymentView
    (L, R) = field_refs(left, right)

    dollars = map_rightward(
        left=L.cents,
        right=R.dollars,
        rightward=lambda cents, *, ctx: cents / ctx["minor_units"],
    )


payment_view = PaymentTwixt().rightward(
    Payment(cents=1210),
    context={"minor_units": 100},
)
```


## What Betwixt isn't

Betwixt intentionally leaves several problems to the libraries and application code that already own them. It does not
validate, serialize, or persist anything. Betwixt recognizes that those problems are best left to the libraries that
already do them very well. Betwixt isn't useful _at all_ on its own. It's entire purpose is to help different app
surfaces that deal with the same data in different ways get the _shape_ of the data they need.


## Installation

The package on PyPI is named `betwixt-data`, while the Python import is `betwixt`.

!!! tip "Sorry for the confusion!"
    When I first started planning Betwixt, I thought the name was available on PyPI. I must not have been careful,
    though, because another `betwixt` packae is registered there since 2020. I only noticed at publication time once
    all the implementation, tests, examples, demos, documentation, and branding had been finished. The code was already
    pushed to GitHub under `dusktreader/betwixt` as well. Instead of coming up with a new name, creating a new logo,
    and rewriting everything with the new name, I just took the lazy path. Betwixt is published to PyPI under
    `betwixt-data`, but everything else after install uses `betwixt`.

```shell
uv add betwixt-data
```

The core package supports dataclasses and `TypedDict`. Pydantic and SQLAlchemy support are optional extras:

```shell
uv add "betwixt-data[pydantic]"
uv add "betwixt-data[sqlalchemy]"
uv add "betwixt-data[pydantic,sqlalchemy]"
```

If you want it to work with other data types, creating a custom adapter is
[very straigtforward](https://dusktreader.github.io/betwixt/adapters/).

If you want to walk through the features before writing a mapping, the package includes a guided demo. To run the
Pydantic and SQLAlchemy examples from this post as well, install all three extras:

```shell
uvx --from "betwixt-data[demo,pydantic,sqlalchemy]" betwixt-demo
```


## Read the docs and try it out

Betwixt is available now as [`betwixt-data` on PyPI](https://pypi.org/project/betwixt-data/). The source is on
[GitHub](https://github.com/dusktreader/betwixt), and the [documentation](https://dusktreader.github.io/betwixt/) has a
quickstart, concepts guide, feature reference, adapter guide, case studies, and complete examples.

I built Betwixt because the code that translates between two perfectly reasonable models was rarely reasonable itself.
Giving that relationship a name and a home makes it easier to read, test, and change. This is the first full-featured
release, so real boundary cases are exactly what I want to see next. If you try it, open an issue with the shape that
made you reach for it.

Thanks!
