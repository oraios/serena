function Invoke-BrokenFactory {
    Invoke-MissingGreeting
}

function Invoke-BrokenConsumer {
    $value = Invoke-BrokenFactory
    Write-Output $value
    Invoke-MissingConsumerValue
}
