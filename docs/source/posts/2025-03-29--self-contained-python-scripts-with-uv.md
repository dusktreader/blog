---
draft: true
date: 2025-03-29
authors:
  - the.dusktreader
categories:
  - dev
tags:
  - Python
  - uv
---

# Self-contained Python scripts with `uv`

!!! tip "TLDR"

    You can add uv into the shebang line for a Python script to make it a self-contained executable.

I am working on a Go project to better learn the language. It's a simple API backed by a postgres database.

When I need to test out an endpoint, I prefer to use the [httpx](https://www.python-httpx.org/) python package inside an
[ipython](https://ipython.org/) REPL over making curl requests. It's nice to be able to introspect responses and easily
package payloads with dicts instead of writing out JSON.

Anyway, I decided to write a script to upsert some user data so that I can beat on my `/users` endpoint.

<!-- more -->

My `jam_users.py` script looks like this:

```python
import httpx
import IPython
from loguru import logger

users = [
    dict(name="The Dude", email="the.dude@abides.com", password="thedudeabides"),
    dict(name="Walter Sobchak", email="walter@sobchak-security.com", password="vietnamvet"),
    dict(name="Donnie", email="donniesurfs@yahoo.com", password="iamthewalrus"),
    dict(name="Maude", email="mauddie@avant-guard.com", password="goodmanandthorough"),
]

r = httpx.get("http://localhost:4000/v1/users")
r.raise_for_status()

for user in r.json()["users"]:
    logger.info(f"Deleting: {user['name']}")
    r = httpx.delete(f"http://localhost:4000/v1/users/{user['id']}")
    r.raise_for_status()

for user in users:
    r = httpx.post("http://localhost:4000/v1/users", json=user)
    r.raise_for_status()
    logger.info(f"Created: {r.json()}")

IPython.embed()
```

This is really straight-forward. It will clear out any existing users and then insert these test users. Right after
that, I get dropped into an `ipython` repl to do what I need for testing. All I have to do is run:

```bash
python jam_users.py
```

However, if I want to run the script as-is, I will need to choose one of these approaches:

* Install the dependencies `httpx`, `IPython`, and `loguru` globally in my system python
* Create a virtual environment, activate it, install deps, and run my script while the venv is activated

These are both not great options in my opinion. These approaches also rely on having a system python installed that is
compatible with these packages. This isn't as big of a problem, but something to consider anyway.

I've been using [uv](https://github.com/astral-sh/uv) a lot lately, and I'm becoming quite enamoured with its usefulness
as a package manager, efficiency as a pip replacement, and abilities for isolated python executables. One thing that I
haven't used much yet are the special `# /// script` tags in a python script.

When I first read about this functionality, I was pretty skeptical. I'm not particularly keen on embedding syntax into
comments. However, this seemed like the perfect application. So, updated my script to include the deps in the script
header like so:

```python
# /// script
# dependencies = ["ipython", "httpx", "loguru"]
# ///
import httpx
import IPython
from loguru import logger

...
```

With this added, now I can run the script really easily with `uv`:

```bash
uv run jam_users.py
```

Great! Now, `uv` will create an isolated virtual environment for the script, download the dependencies and install them,
and then run my script in the context of that venv! I don't have to manage the virtual environment myself nor worry
about cluttering my system python with packages that I will invariably forget to remove later.

One nice thing about a regular Python script, though, is that you can make it executable with a shebang line:

```python
#!/usr/bin/env python
...
```

Now, if I make the script executable (`chmod +x jam_users.py`), I can invoke it directly as an executable script!
However, this won't take advantage of the `uv` script header because Python itself will just ignore the comment.

So, I did some digging and found out that you can actually embed the invocation of the uv command right in the shebang
line like so:

```python
#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["ipython", "httpx", "loguru"]
# ///
import httpx
import IPython
from loguru import logger

...
```

This works because the `-S` flag tells the system to split everything after it into separate arguments before passing it
to the system's `env`.

Now (after `chmod +x jam_users.py`, of course), I can execute my script directly:

```bash
./jam_users.py
```

That's it! What's even better is that I can run this script on any (Unix) system that has `uv` installed without needing
to do ANY dependency or virtual environment management.

Now, this script itself is really trivial and not much more than a toy example. However, in my past I have written
rather complex scripts that I needed to hand off to other users to run. Of course, this always came with a long
explanation of how to _prepare_ their system just to run the script. This approach solves that problem instantly and
painlessly (as long as they have `uv` installed).

Take it for a spin, and let me know your thoughts.

Thanks for reading!
