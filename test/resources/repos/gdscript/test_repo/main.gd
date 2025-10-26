extends Node

const MathUtils = preload("res://src/utils/math_utils.gd")
const Player = preload("res://src/player.gd")

var player: Player

func _ready() -> void:
    var initial_health := MathUtils.double(10)
    player = Player.new(initial_health)
    player.greet("Serena")
    MathUtils.triple(initial_health)
