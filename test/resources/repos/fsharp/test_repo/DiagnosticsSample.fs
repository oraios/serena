module DiagnosticsSample

let brokenConsumerValue = 1

let brokenFactory () =
    missingGreeting

let brokenConsumer () =
    let value = brokenFactory ()
    printfn "%A" value
    missingConsumerValue
