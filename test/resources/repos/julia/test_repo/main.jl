include("lib/helper.jl")

function calculate_sum(a, b)
    return a + b
end

function main()
    result = calculate_sum(5, 3)  # A within-file reference
    println(result)
    Helper.say_hello()            # A cross-file reference
end

main()
