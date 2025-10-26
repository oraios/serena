class_name MathUtils
extends Node

func double(value: int) -> int:
    return value * 2

func triple(value: int) -> int:
    return value * 3

func clamp_to_positive(value: int) -> int:
    if value < 0:
        return 0
    return value
