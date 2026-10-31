.PHONY: lint test attribution

# Test deps are resolved per-run by uv, so there is no venv to create or refresh.
PYTEST = uv run --with pytest --with pyyaml pytest

# Linters run pinned and uninstalled, so a new default rule upstream cannot turn CI red.
MARKDOWNLINT = bunx markdownlint-cli2@0.24.0
RUFF = uvx ruff@0.17.2
SHELLCHECK = uvx --from shellcheck-py==0.11.0.1 shellcheck

# bin/lint-files picks each linter's files by shebang and skips upstream entries.
lint:
	$(MARKDOWNLINT) $$(bin/lint-files markdown)
	$(RUFF) check $$(bin/lint-files python)
	$(SHELLCHECK) $$(bin/lint-files shell)

# PYTHONDONTWRITEBYTECODE keeps pytest's assertion rewriter from leaving __pycache__
# inside a skill directory, which is symlinked whole into each harness.
test:
	PYTHONDONTWRITEBYTECODE=1 $(PYTEST) -q

# Rewrite the README's third-party table from skill-registry.json and licenses.json.
attribution:
	python3 bin/attribution
