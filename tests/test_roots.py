"""Every path a module computes from its own `__file__` points where it claims.

A count of `dirname`s breaks at the first move of the file, silently: the
package move of 2026-09-07 took `config.py` one level deeper, and had the
count stayed, `.env` would have been looked for under `src/` and every secret
would have read as unset. `schema.py` would have globbed nothing and counted
zero everywhere. So each such constant is asserted against a landmark that
only the right directory holds.
"""
import os

from booksmith.core import config, replay, schema
from booksmith.core import knobs
from booksmith.tree import cyr
from booksmith import acceptance
from booksmith.models import paddleocr_vl


def _is_repo_root(p):
    return os.path.isfile(os.path.join(p, "pyproject.toml")) and \
        os.path.isdir(os.path.join(p, "src", "booksmith"))


def _is_package(p):
    return os.path.isfile(os.path.join(p, "__init__.py")) and \
        os.path.isdir(os.path.join(p, "core"))


def test_config_root_is_the_repository():
    assert _is_repo_root(config.ROOT), config.ROOT
    assert config.ENV_FILE == os.path.join(config.ROOT, ".env")


def test_schema_root_is_the_repository():
    assert _is_repo_root(schema.ROOT), schema.ROOT


def test_acceptance_root_is_the_repository():
    assert _is_repo_root(acceptance.ROOT), acceptance.ROOT


def test_cyr_root_is_the_repository():
    assert _is_repo_root(cyr.ROOT), cyr.ROOT
    assert cyr.BASELINE == os.path.join(cyr.ROOT, "cyr-baseline.json")


def test_knobs_src_is_the_package():
    assert _is_package(knobs.SRC), knobs.SRC


def test_replay_pkg_is_the_package():
    assert _is_package(replay.PKG), replay.PKG


def test_the_rented_job_ships_the_whole_package():
    """`spec()` copies `PKG` to the box; two `dirname`s from a file that
    moves is a partial package shipped in silence, learnt on a rented card."""
    assert _is_package(paddleocr_vl.PKG), paddleocr_vl.PKG
