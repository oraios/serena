extends Node

const MathUtils = preload("res://src/utils/math_utils.gd")

func compute_bonus(value: int) -> int:
    return MathUtils.clamp_to_positive(value)
