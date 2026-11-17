from __future__ import annotations

import re
from functools import lru_cache
from datetime import datetime, timezone

from .models import BoxSpec
from .naming import fmt_num, stl_filename


class TemplateError(ValueError):
    pass


@lru_cache(maxsize=None)
def _assignment(name: str) -> re.Pattern:
    return re.compile(rf"^(\s*{re.escape(name)}\s*=\s*)([^;]+)(;.*)$", re.M)


_FN = re.compile(r"^\s*\$fn\s*=\s*[^;]+;", re.M)


def set_var(src: str, name: str, value: float | int) -> str:
    new, count = _assignment(name).subn(lambda m: f"{m.group(1)}{fmt_num(value)}{m.group(3)}", src, count=1)
    if count != 1:
        raise TemplateError(f"variable '{name}' not found exactly once")
    return new


def render_body(template: str, spec: BoxSpec, fn: int = 64) -> str:
    """The generated SCAD without the timestamp header; stable, so usable as a cache key."""
    result = template
    for name in ("length", "width", "height", "wall", "r", "cover_width"):
        result = set_var(result, name, getattr(spec, name))
    return _FN.sub(f"$fn = {int(fn)};", result, count=1)


def with_header(body: str, spec: BoxSpec) -> str:
    return f"// GridDrawer generated {datetime.now(timezone.utc).isoformat()} {stl_filename(spec)}\n" + body


def render_scad(template: str, spec: BoxSpec, fn: int = 64) -> str:
    return with_header(render_body(template, spec, fn), spec)
