from .models import BoxSpec


def fmt_num(value: float) -> str:
    rounded = round(float(value), 3)
    return f"{rounded:.3f}".rstrip("0").rstrip(".")


def stl_filename(spec: BoxSpec) -> str:
    return f"{fmt_num(spec.width)}X{fmt_num(spec.length)}.stl"
