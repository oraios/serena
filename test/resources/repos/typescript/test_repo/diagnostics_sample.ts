export function brokenFactory(): string {
    return missingGreeting;
}

export function brokenConsumer(): void {
    const value = brokenFactory();
    console.log(value);
    console.log(missingConsumerValue);
}
