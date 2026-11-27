"""The suite must not inherit the repository a git hook was started from."""

import os

import pytest

from conftest import GIT_REPOSITORY_VARIABLES


@pytest.mark.parametrize("name", GIT_REPOSITORY_VARIABLES)
def test_git_repository_variables_are_absent(name):
    assert name not in os.environ
