def brokenFactory : Nat :=
  missingGreeting

def brokenConsumer : Nat :=
  let value := brokenFactory
  value + missingConsumerValue
