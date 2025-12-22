package com.example

object Main {
  def main(args: Array[String]): Unit = {
    println("Hello, Scala!")
    
    // Use Utils from another file
    Utils.printHello()
    val result = Utils.multiply(3, 4)
    println(s"3 * 4 = $result")

    // Call local methods
    val sum = add(5, 3)
    println(s"5 + 3 = $sum")
  }

  def add(a: Int, b: Int): Int = {
    a + b
  }

  // https://github.com/oraios/serena/issues/688
  def someMethod(config: Config): Unit = {
    val str = config.field1

    println(str)
  }
  
  case class Config(field1:String)
}
