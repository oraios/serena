package test_repo

fun brokenFactory(): String {
    return missingGreeting
}

fun brokenConsumer() {
    val value = brokenFactory()
    println(value)
    println(missingConsumerValue)
}
