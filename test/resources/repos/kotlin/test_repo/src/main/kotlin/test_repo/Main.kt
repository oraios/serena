package test_repo

object Main {
    @JvmStatic
    fun main(args: Array<String>) {
        Utils.printHello()
        val model = Model("Cascade")
        println(model.name)
        acceptModel(model)
    }

    fun acceptModel(m: Model?) {
        // Do nothing, just for LSP reference
    }
}