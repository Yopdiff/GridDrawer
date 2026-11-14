from __future__ import annotations

import re
from datetime import datetime, timezone

from .models import BoxSpec
from .naming import fmt_num, stl_filename


class TemplateError(ValueError):
    pass


def set_var(src: str, name: str, value: float | int) -> str:
    pattern = re.compile(rf"^(\s*{re.escape(name)}\s*=\s*)([^;]+)(;.*)$", re.M)
    new, count = pattern.subn(lambda m: f"{m.group(1)}{fmt_num(value)}{m.group(3)}", src, count=1)
    if count != 1:
        raise TemplateError(f"variable '{name}' not found exactly once")
    return new


def render_scad(template: str, spec: BoxSpec, fn: int = 64) -> str:
    result = template
    for name in ("length", "width", "height", "wall", "r", "cover_width"):
        result = set_var(result, name, getattr(spec, name))
    result = re.sub(r"^\s*\$fn\s*=\s*[^;]+;", f"$fn = {int(fn)};", result, count=1, flags=re.M)
    header = f"// GridDrawer generated {datetime.now(timezone.utc).isoformat()} {stl_filename(spec)}\n"
    return header + result
