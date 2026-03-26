package util;

/** Utility class providing helper functions used by other modules. **/
class Helper {
    /** Format a message by adding brackets around it. **/
    public static function formatMessage(msg:String):String {
        return '[ $msg ]';
    }

    /** Add two numbers together. **/
    public static function addNumbers(a:Int, b:Int):Int {
        return a + b;
    }

    /** Multiply two numbers. **/
    public static function multiplyNumbers(a:Int, b:Int):Int {
        return a * b;
    }
}
