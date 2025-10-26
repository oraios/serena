extends Node

const Player = preload("res://src/player.gd")

func generate_player() -> Player:
    var generated := Player.new()
    generated.heal(1)
    return generated
