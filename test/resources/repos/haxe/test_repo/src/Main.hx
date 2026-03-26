package;

import model.User;
import model.Role;
import util.Helper;

/**
    Main entry point for the Haxe test application.
    Used to test symbol discovery, references, and cross-file navigation.
**/
class Main {
    static var appName:String = "TestApp";

    static function main():Void {
        var user = new User("Alice", Role.Admin);
        var greeting = greet(user.getName());
        var sum = Helper.addNumbers(5, 10);
        trace(greeting);
        trace('Sum: $sum');
    }

    static function greet(name:String):String {
        return Helper.formatMessage('Hello, $name!');
    }
}
