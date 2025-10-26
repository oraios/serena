class_name Player
extends Node

var health: int

func _init(start_health: int = 100) -> void:
    health = start_health

func greet(name: String) -> void:
    print("Hello %s, health is %d" % [name, health])

func heal(amount: int) -> void:
    health += amount

func is_alive() -> bool:
    return health > 0
