package com.example

object Main {
  def main(args: Array[String]): Unit = {
    println("Hello, Scala!")
    
    // Use Utils from another file
    Utils.printHello()
    val result = Utils.multiply(3, 4)
    println(s"3 * 4 = $result")
    
    // Use case classes from Model.scala
    val user = User("Alice", 30)
    println(user.greet())
    
    val product = Product(1, "Laptop", 999.99)
    println(product.displayInfo())
    
    // Call local methods
    val sum = add(5, 3)
    println(s"5 + 3 = $sum")
    
    processUser(user)
  }

  def add(a: Int, b: Int): Int = {
    a + b
  }
  
  def processUser(user: User): Unit = {
    println(s"Processing user: ${user.name}")
  }
}
