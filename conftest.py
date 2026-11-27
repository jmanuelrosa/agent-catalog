"""Keep the caller's git repository variables out of the test run.

Git hooks run with GIT_DIR set to the real repository, and scratch repositories created by
the tests inherit it, so their git commands would write into the developer's own checkout.
"""

import os

GIT_REPOSITORY_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX")

for _name in GIT_REPOSITORY_VARIABLES:
    os.environ.pop(_name, None)
