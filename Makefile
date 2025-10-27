default: help


## ==== Documentation ==================================================================================================

docs: docs/build  ## Shortcut for docs/serve

docs/build:  ## Build the documentation
	@uv run mkdocs build --config-file=docs/mkdocs.yaml

docs/serve:  ## Build the docs and start a local dev server
	@uv run mkdocs serve --config-file=docs/mkdocs.yaml --dev-addr=localhost:10000


## ==== Helpers ========================================================================================================

clean:  ## Clean up build artifacts and other junk
	@rm -rf .venv
	@uv run pyclean . --debris
	@rm -rf dist
	@rm -rf .ruff_cache
	@rm -rf .pytest_cache
	@rm -rf .mypy_cache
	@rm -f .coverage*
	@rm -f .junit.xml

help:  ## Show help message
	@awk "$$PRINT_HELP_PREAMBLE" $(MAKEFILE_LIST)


## ---- Make configuration ---------------------------------------------------------------------------------------------

.ONESHELL:
SHELL:=/bin/bash
.PHONY: default docs docs/build docs/serve clean help


## ---- Hidden auxiliary targets ---------------------------------------------------------------------------------------

_confirm:  # Requires confirmation before proceeding (Do not use directly)
	@echo -n "Are you sure? [y/N] " && read ans && [ $${ans:-N} = y ]


## ---- Help printer ---------------------------------------------------------------------------------------------------

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
