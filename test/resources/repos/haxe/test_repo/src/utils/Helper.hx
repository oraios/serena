package utils;

/**
 * Utility functions for the Haxe test application.
 *
 * This class provides helper functions used by the Main class.
 */
class Helper {
	/**
	 * Format a message by adding brackets around it.
	 */
	public static function formatMessage(msg:String):String {
		return "[ " + msg + " ]";
	}

	/**
	 * Add two numbers together.
	 */
	public static function addNumbers(x:Int, y:Int):Int {
		return x + y;
	}

	/**
	 * Multiply two numbers.
	 */
	public static function multiplyNumbers(x:Int, y:Int):Int {
		return x * y;
	}
}
