import utils.Helper;

/**
 * Main class for testing Haxe language server functionality.
 *
 * This class tests:
 * - Symbol discovery (class, methods, fields)
 * - Within-file references
 * - Cross-file references to utils.Helper
 */
class Main {
	var message:String;
	var count:Int;

	public function new() {
		message = greet("World");
		count = Helper.addNumbers(5, 10);
	}

	/**
	 * Greet someone by name.
	 */
	public function greet(name:String):String {
		return "Hello, " + name + "!";
	}

	/**
	 * Calculate and return the formatted result.
	 */
	public function calculateResult():String {
		var sum = Helper.addNumbers(count, 20);
		var formatted = Helper.formatMessage(message);
		return formatted + " (sum: " + Std.string(sum) + ")";
	}

	public static function main() {
		var app = new Main();
		Sys.println(app.calculateResult());
	}
}
