extends Node

const Player = preload("res://src/player.gd")

func spawn_npc() -> Player:
    var npc := Player.new()
    npc.heal(5)
    return npc
