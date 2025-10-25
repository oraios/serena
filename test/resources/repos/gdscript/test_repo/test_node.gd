extends Node

# A simple GDScript test file
var test_variable: int = 42

func _ready() -> void:
    print("Test node is ready")

func test_function() -> void:
    print("This is a test function")
    return test_variable

func another_function(value: int) -> int:
    return value * 2