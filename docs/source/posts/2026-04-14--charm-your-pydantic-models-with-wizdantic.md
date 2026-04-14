---
date: '2026-04-14'
authors:
- the.dusktreader
comments: true
---

# Charm your Pydantic models with Wizdantic

!!! tip "TLDR"
    Conjure populated Pydantic models from thin air with an interactive terminal wizard.


CLI tools that need structured configuration often end up with a maze of input() calls, hand-rolled validation, and
forgotten edge cases. If you already have a Pydantic model describing that configuration, wizdantic turns it into an
interactive wizard with a single function call. You define the shape of the data once, and the wizard handles the rest.

<!-- more -->

## Background

I (somewhat) recently released a toolkit for building stateful CLI apps named
[typerdrive](https://dusktreader.github.io/typerdrive/) that provides a lot of capability for managing app settings
through Pydantic models. However, for a relatively complex settings model, invoking the single [`bind` command](
    https://dusktreader.github.io/typerdrive/features/settings/#bind
) to provide all your settings becomes pretty onerous. Further, providing guidance to your user about the expected
types and constraints is not easy.

I needed to release a new internal tool at my company, and I wanted other developers to have a good experience. So,
I hand-rolled a wizard to collect the settings. It worked really well, and I started thinking about how useful it
would be to be able to drive the wizard automatically based on the settings' Pydantic model. It had all the type
hints and constraints already, so there should be a tool that can use that to guide users in setting up the app.

So, I took some time (turned out, way more than I expected!) to build such a tool. Enter [Wizdantic](
    https://dusktreader.github.io/wizdantic/
). Instead of rolling the wizard tool directly in to typerdrive, I decided to make it a stand-alone package that
any CLI tool builder can use with their Pydantic models.


## How it works

When you call `run_wizard(MyModel)`, wizdantic inspects your model's type annotations and builds a prompt
strategy for each field. Scalars (`str`, `int`, `float`) get a plain text prompt. Booleans get a `y/n` confirm.
Enums and `Literal` types display a numbered menu. `SecretStr` fields use masked input. Collections (`list`, `set`,
`tuple`, `dict`) accept either JSON or a comma-separated shorthand. Optional fields accept blank input and return
`None`. If you pass a value that can't be parsed or validated as its given type, the wizard shows you the Pydantic error
and re-prompts for a new value. No partial models make it past the wizard's stern gaze.

Wizdantic can also handle nested `BaseModel` fields. For these, the wizard recurses into a sub-wizard, then hands the
constructed instance back up to the parent. Collections of models work the same way, except the sub-wizard runs
in a loop, asking "Add another?" after each entry. Fixed-length tuples with model positions skip the loop and
prompt each position exactly once. You can nest as deep as you like; it's turtles all the way down.

`WizardLore` is the annotation type that lets you tune individual field behavior. Attach it inside
`Annotated[...]` alongside your `Field(...)`. You can override the format hint, plug in a custom parser
callable, or assign the field to a named section. Sections group related prompts under a colored heading during the run
and in the summary table printed at the end. The whole thing is driven by Rich, so if you need to redirect output
or set a specific terminal width, you can pass your own `Console` instance.


## Setting it up

Just `uv add` it and you're off:

```shell-ps1
uv add wizdantic
```

!!! note ">= Python 3.12"
    Wizdantic requires Python 3.12 or later.

Wizdantic does bring a few dependencies along with it. The most notable of these are:

- **rich**: for rich text rendering
- **prompt_toolkit**: for editing responses and recalling previous entries with up arrow
- **py-buzz**: for enhanced exceptions
- **snick**: for basic text arrangement
- **inflection**: for title-izing strings
- **pydantic**: for, well, the model!


## Examples

### Basic wizard

The simplest case: a flat model where every field is a scalar.

```python title="register_spell.py"
from typing import Annotated
from pydantic import BaseModel, Field
from wizdantic import run_wizard


class Spell(BaseModel):
    name: Annotated[str, Field(description="Spell name")]
    casting_time: Annotated[int, Field(description="Casting time in seconds")] = 6
    power_level: Annotated[float, Field(description="Raw arcane power output")] = 1.0
    cursed: Annotated[bool, Field(description="Carries a curse upon casting")] = False


if __name__ == "__main__":
    spell = run_wizard(Spell, title="Register a Spell")
```

```shell-ps1
python register_spell.py
```

The wizard prompts for each field in order. `name` has no default so it insists on a value. The rest show
their defaults; press Enter to keep them or type something new. When the last field is done, a summary table
is printed and you get back a fully validated `Spell` instance.

Here is what a run of this wizard might look like:

```
─────────────────────────────────────── Register a Spell ────────────────────────────────────────

Spell name (name): Summa Obliteratio
Casting time in seconds (casting_time) (6):
Raw arcane power output (power_level) (1.0): 9001
Carries a curse upon casting (cursed) [y/n] (n): y

                     Summary
 Field                         Value
 Spell name                    Summa Obliteratio
 Casting time in seconds       6
 Raw arcane power output       9001.0
 Carries a curse upon casting  True
```


### Nested model with sections

A more involved example: a nested model with fields grouped into sections using `WizardLore`.

```python title="register_ritual.py"
from typing import Annotated
from pydantic import BaseModel, Field
from wizdantic import WizardLore, run_wizard


class Caster(BaseModel):
    name: Annotated[str, Field(description="Caster's name")]
    school: Annotated[str, Field(description="School of magic")] = "Evocation"


class Ritual(BaseModel):
    title: Annotated[str, Field(description="Ritual title"), WizardLore(section="Overview")]
    location: Annotated[str, Field(description="Where the ritual is performed"), WizardLore(section="Overview")]
    caster: Annotated[Caster, Field(description="Officiant")]
    components: Annotated[list[str], Field(description="Required components")] = []


if __name__ == "__main__":
    ritual = run_wizard(Ritual, title="Plan a Ritual")
```

```shell-ps1
python register_ritual.py
```

The `Overview` section heading appears before `title` and `location`. When the wizard reaches `caster`, it
drops into a sub-wizard with a magenta heading to collect the `Caster` fields, then returns to the parent.
`components` accepts a comma-separated list or a JSON array.

Here is what a run of this wizard might look like:

```
───────────────────────────────────────── Plan a Ritual ─────────────────────────────────────────

─────────────────────────────────────────── Overview ────────────────────────────────────────────
Ritual title (title): Dominous Daemonium Liga
Where the ritual is performed (location): Summoning Circle
───────────────────────────────────────────── Other ─────────────────────────────────────────────

─────────────────────────────────────────── Officiant ───────────────────────────────────────────

Caster's name (name): Eiric Voss
School of magic (school) (Evocation):
Required components (components) (str, str, ...) (JSON array or comma-separated list): salt, candles, holy water

                           Summary
 Field                          Value
 Ritual title                   Dominous Daemonium Liga
 Where the ritual is performed  Summoning Circle
 Officiant                       Field            Value
                                 Caster's name    Eiric Voss
                                 School of magic  Evocation
 Required components            salt, candles, holy water
```

## Try the demo

If you want to see the full range of supported field types before writing any code, wizdantic ships a demo
that covers everything: scalars, booleans, enums, secrets, optionals, collections, nested models, sections,
and more. Install the `demo` extra and run it:

```shell-ps1
uv add "wizdantic[demo]"
wizdantic-demo
```

Or, you can try the demo directly using `uvx`:

```shell-ps1
uvx --from=wizdantic[demo] wizdantic-demo
```

## Conclusion

If you already have a Pydantic model, you're most of the way to a full interactive wizard. The type
hints and field constraints you wrote for validation are all wizdantic needs to drive the prompts. You
don't define the wizard separately; the model *is* the wizard configuration. `WizardLore` is there when
you need extra control, but most models work without it.

I built wizdantic to scratch my own itch, but I tried to make it general enough that you can drop it into any
CLI tool that collects structured input. If you run into a field type it doesn't handle, or something behaves
unexpectedly, open an issue on [GitHub](https://github.com/dusktreader/wizdantic). I'm looking forward to this
project growing through real usage.

I'm going to start exercising it with a new `typerdrive` subcommand that will use it to initialize your
`typerdrive` app (coming soon):

```shell-ps1
my-typerdrive-app settings wizard
```

Let me know what you think in the comments!
