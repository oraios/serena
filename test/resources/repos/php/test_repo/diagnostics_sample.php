<?php

function brokenFactory(): string {
    return $missingGreeting;
}

function brokenConsumer(): void {
    $value = brokenFactory();
    echo $value;
    echo $missingConsumerValue;
}
