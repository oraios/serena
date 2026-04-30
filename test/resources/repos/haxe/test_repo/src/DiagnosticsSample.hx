class DiagnosticsSample {
    static function brokenFactory():String {
        return missingGreeting;
    }

    static function brokenConsumer():Void {
        trace(brokenFactory());
        trace(missingConsumerValue);
    }
}
