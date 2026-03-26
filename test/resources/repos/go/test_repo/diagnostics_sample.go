package main

func brokenFactory() string {
    return missingGreeting
}

func brokenConsumer() {
    value := brokenFactory()
    _ = value
    _ = missingConsumerValue
}
