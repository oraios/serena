int brokenFactory() {
    return missingGreeting;
}

int brokenConsumer() {
    int value = brokenFactory();
    return value + missingConsumerValue;
}
