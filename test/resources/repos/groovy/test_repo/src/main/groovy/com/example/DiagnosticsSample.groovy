package com.example

class DiagnosticsSample {
    static String brokenFactory() {
        missingGreeting
    }

    static void brokenConsumer() {
        def value = brokenFactory()
        println(value)
        println(missingConsumerValue)
    }
}
