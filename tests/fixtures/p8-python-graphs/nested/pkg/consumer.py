from pkg.target import target_value
from app.service import Service  # cross-unit, must not traverse


def consume():
    return target_value()
