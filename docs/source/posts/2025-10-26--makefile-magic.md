---
date: 2025-10-26
authors:
- the.dusktreader
comments: true
tags:
- make
categories:
- dev-tools
---

# Makefile magic

!!! tip "TLDR"
    I have a cool structure, nice convenience functions, and flashy magic that "makes" my projects pretty awesome!

For a fairlylong time, now, I've been including a `Makefile` in all of my projects. It's a nice way to provide
access to actions that need to be done over-and-over in a software project. It's familiar (to most folks), works
on almost any reasonable dev environment out-of-the box, and makes getting started on the project really
straightforward.

Over the years, I've developed a lot of cool stuff that I like to include in my `Makefiles`. This ranges from some
basic patterns and structures that I've found helpful to some fancy "magic" that makes it nice to work with.

Today, I decided to create a [GitHub repo](https://github.com/dusktreader/Makefile) to showcase these patterns in
a few example `Makefile` entries. I thought it might be nice to talk through what's offered there and explain some
of the deeper magic.


<!-- more -->


## Why `make`?

I will be the _first_ to admit that the syntax and structure of `Makefiles` is _awful_. It feels very dated, it's
not obvious at all to newcomers, and its scope doesn't really match most modern projects that aren't building
C and C++ apps.

Well, the first reason is that `make` is ubiquitous. I work almost exclusively in Unix-like environments, and it's
a good bet that these systems will have `make` already when I log in for the first time.

Now, almost all modern projects have some sort of dependencies that you will have to download and install before
you can start working. Still, there's something comforting about having a bit of project management software that
works _right away_ without having to do anything else.

The last big reason, for me, is that it's truly cross platform and multi-lingual. I really _hate_ having to install
some `npm` package to get started on a Python project. Conversely, I don't want to have to install a Python
application to operate project management for a Node project. It just feels...off to me.

So, forget all that. Use `make` and just get to work!


## It's been a long road

My first exposure to `Makefile` was a couple of decades ago in my `Software Engineering Tools` class that was a
required course for my University's (Go [Cougs](https://wsu.edu)!) Computer Science program at the time. The
curriculum was entirely Linux-based, and we were taught how to use a lot of tools involved in working in a Linux
development environment circa 2005. One of these was obviously `make`.

At the time, the program's foundation was C++ development. I was broke as hell, so getting a Visual Studio license
was pretty much out of the question. Plus, I was determined to learn how to be efficient in Linux. Thus, I
embraced `make` and the Linux tool-chain for building C++ apps.

These days, I don't really write any C or C++. Still, I find the familiarity and convenience of `Makefile`
comforting and efficient for my daily workflows.

Enough about ancient history, lets dig into the `Makefile` examples and see my cool stuff!


## Sections and basic targets

One of the first things I've found essential over the years is organizing the `Makefile` by sections.
Without it, the file becomes an impenetrable mess of targets without any rhyme or reason to the ordering.

So, I like to break it up into sections. I designate sections of my `Makefile` like this:

```Makefile
## ==== Basic targets ==================================================================================================

basic: ## Just a basic target with nothing fancy
	@echo Executing basic target

simple: ## Just a simple target that's very straightforward
	@echo Executing simple target
```

As you'll see later, the _format_ of the section headers is actually significant as are the comments for each of the
targets. These are used to generate a nicely formatted `help` output for my `Makefile`. But, as you can see here, they
are still very human-readable and helpful when you are navigating the Makefile


## Targets with prerequisites

A fundamental element of `Makefile` syntax is specifying `prerequisites` for a given target. These tell `make` to only
run the target if the file or target described by the prereq exists. While this is `extremely` useful in specifying
build chains in C++ and C projects, for other projects it can be a nice way to simply say, _also_ run this other
target whenever I run this one.

For example, we could provide a simple prereq for a target like this:

```Makefile
basic: ## Just a basic target with nothing fancy
	@echo Executing basic target

dependent: basic ## Just a target that will first run basic
	@echo Executing dependent target
```

Running:

```shell
make dependent
```

Will result in output:

```
Executing basic target
Executing dependent target
```

It's important to note that prerequisites can be _filenames_ as well as other targets in the makefile. This can be
used as a sort of guard to make sure that the target can't be run unless a specific file exists:

```Makefile
migrate-db: .env  ## Migrate the database (only if .env file has been prepared)
    uv run alembic migrate
```

You can read more about prerequisites in the
[official `make` documentation](https://www.gnu.org/software/make/manual/html_node/Prerequisite-Types.html).


## Targets with patterns

Now, for C++ and C development, patterns are essential. This lets you specify that each `.c` file needs to have a
`.o` file generated for it. In a C `Makefile`, you might have a target like:

```Makefile
%.o: %.c
    gcc $(CFLAGS) -c $< -o $@
```

This is gibberish for folks that haven't used `make` before. It just means, if there isn't a `.o` file for each `.c`
file in the directory, compile one with your specified flags (if any).

However, for other software projects, patterns can still be a really nice way to control behavior in the target. For
example, imagine that you want to be able to target different environments with a `make` command. You can use a
pattern in the target to specify that.

```Makefile
publish/%:
    @bash publish.sh $(notdir $@)
```

Here, the `%` in the target line `publish/%` is the pattern. In the next line, we can reference the value provided
in the pattern using `$(notdir $@)`. This just tells `make` to use the name of the current target, but leave out the
"dir" (anything before the final `/`).

In this way, running:

```shell
make publish/qa
```

Will run the `publish.sh` script with `qa` as an argument.

You can read more about patterns in the
[official `make` documentation](https://www.gnu.org/software/make/manual/html_node/Pattern-Rules.html).


## Targets that use variables

Often, I need a target to be provided optional values that change the behavior. In such a case, patterns won't
actually fit the bill. This is especially true if there are more than one optional variables that might need
to be passed in. For these sorts of targets, we can use variables.

Consider a target that can have a `--log-level` flag provided to the shell command. By default, I want to use
a sensible log level, but in some cases I may want something more verbose. I could use this pattern to accomplish
this:

```Makefile
LOG_LEVEL ?= WARN

ingest:
    uv run ingest --log-level=$(LOG_LEVEL)
```

Here, if I do not provide a `LOG_LEVEL` value in my `make` command, the `ingest` process will default to the
"WARN" level. However, if I want to be more verbose, I can supply the value for the variables like this:

```bash
make ingest LOG_LEVEL=DEBUG
```

You can read _a lot_ more about variable management in `Makefiles` in the
[official `make` documentation](https://www.gnu.org/software/make/manual/html_node/Using-Variables.html)


## Targets with guards

One type of prerequisite that I've found really useful is a "guard" target that ensures some condition is met
before executing the command. You can make a guard that checks pretty much anything, but there are three
that I've found the most useful


### Ensure exists guard

The first is a guard that ensures that some file exists before it will let a target run. This can be
implemented like so:

```Makefile
_guard_env:  # Ensures a .env file has been prepared
	@if [[ ! -e ".env" ]]; then \
		echo -e "No .env found! Prepare one first according to the README."; \
		exit 1; \
	fi

start: _guard_env ## Bring all containers up.
	docker compose up -d
```

If I run `make start` before a `.env` file has been prepared, `make` will refuse to proceed and tell
me that I need to set one up.


###  Valid pattern guard

The next guard that is useful is a guard that ensures that the supplied pattern is valid for the command.
This could be implemented as:

```Makefile
VALID_ENV := dev qa staging

_guard_env/%:  # Ensures a valid env is selected (Do not use directly)
	@if ! echo "$(VALID_ENV)" | grep -q "\b$(notdir $@)\b"; \
	then \
		echo -e "Invalid ENV:      $(RED)$(notdir $@)$(CLEAR)"; \
		echo -e "Valid ENV values: $(GREEN)$(VALID_ENV)$(CLEAR)"; \
		echo; \
		exit 1; \
	fi

migrate/%: _guard_env/%  ## Apply migrations in the database
    uv run alembic upgrade $(notdir $@)
```

With this guard, I can be sure that the target can only be run against the allowed environments. This
could prevent me from accidentally applying a migration in production!


### Valid variable guard

This guard is almost identical to the "Valid pattern guard". However, it checks a supplied variable
to make sure that it is valid:

```Makefile
VALID_ENV := dev qa staging
ENV ?= dev

_guard_env:  # Ensures a valid env is selected (Do not use directly)
	@if ! echo "$(VALID_ENV)" | grep -q "\b$(ENV)\b"; \
	then \
		echo -e "Invalid ENV:      $(RED)$(ENV)$(CLEAR)"; \
		echo -e "Valid ENV values: $(GREEN)$(VALID_ENV)$(CLEAR)"; \
		echo; \
		exit 1; \
	fi

migrate: _guard_env  ## Apply migrations in the database
    uv run alembic upgrade ENV=$(ENV)
```


## Targets requiring confirmation

A lot of times, my `Makefile` will contain some targets that can do irreversible things that I don't
want to trigger by accident. For these, it's nice to include a confirmation that ensures that I
_really_ mean to run that target. A confirmation can be defined like this:

```Makefile

_confirm:  # Requires confirmation before proceeding (Do not use directly)
	@echo -n "Are you sure? [y/N] " && read ans && [ $${ans:-N} = y ]

tear-down: _confirm  ## Bring down and destroy all containers.
	docker compose down --remove-orphans
```

When I run `make tear-down` I will be prompted before the command executes:

```shell
$ make tear-down
Are you sure? [y/N]
docker compose down --remove-orphans
[+] Running 3/3
 ✔ Container makefile-db-1   Removed                                                                                                                                                                                                                                                                  0.2s
 ✔ Container makefile-api-1  Removed                                                                                                                                                                                                                                                                  0.2s
 ✔ Network makefile_default  Removed                                                                                                                                                                                                                                                                  0.2s
 ```

 If I had answered "N" (or anything else), the command would have been aborted.


## The deep magic of the `help` target

Something I can't live without anymore is a `help` target that prints out the available targets.
There are lots of recipes out there for this kind of a target, and lots of them provide absolutely
impenetrable one-liners that you just have to use with a bit of faith.

Well, after using a few of these recipes over the years, I finally decided to break down and make
one of my own that isn't just an unreadable mess that flies off the right side of the editor
screen.

While this recipe _is_ an awk program, it is a bit more readable than some others I've seen. I
elected to use `awk` because, like `make`, it's pretty ubiquitous. Additionally, the program is
pretty terse and doesn't inflate my Makefiles to a crazy degree.

Here is the code that makes it work:

```Makefile
RED    := \033[31m
GREEN  := \033[32m
YELLOW := \033[33m
BLUE   := \033[34m
TEAL   := \033[36m
CLEAR  := \033[0m


define PRINT_HELP_PREAMBLE
BEGIN {
	print "Usage: $(YELLOW)make <target>$(CLEAR)"
	print
	print "Targets:"
}
/^## =+ [^=]+ =+.*/ {
    s = $$0
    sub(/^## =+ /, "", s)
    sub(/ =+/, "", s)
	printf("\n  %s:\n", s)
}
/^[$$()% 0-9a-zA-Z_\/-]+(\\:[$$()% 0-9a-zA-Z_\/-]+)*:.*?##/ {
    t = $$0
    sub(/:.*/, "", t)
    h = $$0
    sub(/.?*##/, "", h)
    printf("    $(YELLOW)%-19s$(CLEAR) $(TEAL)%s$(CLEAR)\n", t, h)
}
endef
export PRINT_HELP_PREAMBLE

help:  ## Show help message
	@awk "$$PRINT_HELP_PREAMBLE" $(MAKEFILE_LIST)
```

The first few lines just define some colors that will be used in rendering the help text. It's
just a bit of sugar that makes looking at the generated output a little nicer.

Next, I use `define` to specify the `awk` program. I do this because it works kind of like a
HEREDOC and lets me write out the code without having to escape all the newlines with ugly "\"
characters.

The program itself finds lines that look like `## ==== Section ====` and uses the text as
section headers for the targets. Then, it finds targets that include a `## comment` and prints
them out including the comment text. If a target doesn't have a `## comment`, it will not appear
in the help output.

Finally, I export the defined block as an environment variable that can be referenced in the
help target. Finally, the `help` target itself runs the program in `awk` against all of the
`Makefile` targets passed to the `make` command.

If you want to dive deeper into what's going in the `awk` program itself....well, you can have a
nice adventure learning about the
[awk programming language](https://www.gnu.org/software/gawk/manual/gawk.html)!


## Other stuff

Here are some other things I like to have in my `Makefile`:


### `.PHONY` specifiers

I use `.PHONY` specifiers to tell `make` that my targets won't actually generate files
that match them:

```Makefile
.PHONY: default build migrate clean help
```


### SHELL vars

I like to use these two variable settings to tell `make` to use `bash` for its shell and to
use the same shell for each command in a given target:

```Makefile
SHELL := /bin/bash
.ONESHELL:
```


### Default target

You can use a special variable called `.DEFAULT_GOAL` to describe which target (usually `help`)
should be run if no explicit target is given. However, I think it's a lot more readable to
just create a `default` target in the `Makefile`:

```Makefile
default: help
```


## Conclusion

That pretty much covers what I do in my `Makefiles` these days. I'm sure in a few months, I'll
have to come back and update this with a few more patterns or improvements that I've found.
Still, I hope this is helpful and gives you some ideas about ways you can structure your own
`Makefile` to make your project friendlier for others to work on or just for you to come back
to after a few months.

Check out my [Makefile](https://github.com/dusktreader/Makefile) repository to see some complete
examples.

Thanks for reading!
