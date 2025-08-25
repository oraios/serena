package com.example

case class User(name: String, age: Int) {
  def greet(): String = {
    s"Hello, my name is $name and I am $age years old"
  }
}

case class Product(id: Int, name: String, price: Double) {
  def displayInfo(): String = {
    s"Product: $name (ID: $id) - Price: ${price}"
  }
}
