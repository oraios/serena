package com.example

object DiagnosticsSample {
  def brokenFactory(): String = missingGreeting
  def brokenConsumer(): Unit = {
    println(brokenFactory())
    println(missingConsumerValue)
  }
}
