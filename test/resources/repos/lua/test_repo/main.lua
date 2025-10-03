#!/usr/bin/env lua

-- main.lua: Entry point for the test application

local calculator = require("src.calculator")
local utils = require("src.utils")

local function print_banner()
    print("=" .. string.rep("=", 40))
    print("       Lua Test Repository")
    print("=" .. string.rep("=", 40))
end

local function test_calculator()
    print("\nTesting Calculator Module:")
    print("5 + 3 =", calculator.add(5, 3))
    print("10 - 4 =", calculator.subtract(10, 4))
    print("6 * 7 =", calculator.multiply(6, 7))
    print("15 / 3 =", calculator.divide(15, 3))
    print("2^8 =", calculator.power(2, 8))
    print("5! =", calculator.factorial(5))
    
    local numbers = {5, 2, 8, 3, 9, 1, 7}
    print("Mean of", table.concat(numbers, ", "), "=", calculator.mean(numbers))
    print("Median of", table.concat(numbers, ", "), "=", calculator.median(numbers))
end

local function test_utils()
    print("\nTesting Utils Module:")
    
    -- String utilities
    print("Trimmed '  hello  ' =", "'" .. utils.trim("  hello  ") .. "'")
    local parts = utils.split("apple,banana,orange", ",")
    print("Split 'apple,banana,orange' by ',' =", table.concat(parts, " | "))
    print("'hello' starts with 'he' =", utils.starts_with("hello", "he"))
    print("'world' ends with 'ld' =", utils.ends_with("world", "ld"))
    
    -- Table utilities
    local t1 = {a = 1, b = 2}
    local t2 = {b = 3, c = 4}
    local merged = utils.table_merge(t1, t2)
    print("Merged tables: a=" .. (merged.a or "nil") .. 
          ", b=" .. (merged.b or "nil") .. 
          ", c=" .. (merged.c or "nil"))
    
    -- Logger
    local logger = utils.Logger:new("TestApp")
    logger:info("Application started")
    logger:debug("Debug information")
    logger:warn("This is a warning")
end

local function interactive_calculator()
    print("\nInteractive Calculator (type 'quit' to exit):")
    while true do
        io.write("Enter operation (e.g., '5 + 3'): ")
        local input = io.read()
        
        if input == "quit" then
            break
        end
        
        -- Simple parser for basic operations
        local a, op, b = input:match("(%d+)%s*([%+%-%*/])%s*(%d+)")
        if a and op and b then
            a = tonumber(a)
            b = tonumber(b)
            local result
            
            if op == "+" then
                result = calculator.add(a, b)
            elseif op == "-" then
                result = calculator.subtract(a, b)
            elseif op == "*" then
                result = calculator.multiply(a, b)
            elseif op == "/" then
                local success, res = pcall(calculator.divide, a, b)
                if success then
                    result = res
                else
                    print("Error: " .. res)
                    goto continue
                end
            end
            
            print("Result: " .. result)
        else
            print("Invalid input. Please use format: number operator number")
        end
        
        ::continue::
    end
end

-- Main execution
local function main(args)
    print_banner()
    
    if #args == 0 then
        test_calculator()
        test_utils()
    elseif args[1] == "interactive" then
        interactive_calculator()
    elseif args[1] == "test" then
        test_calculator()
        test_utils()
        print("\nAll tests completed!")
    else
        print("Usage: lua main.lua [interactive|test]")
    end
end

-- Run main function
main(arg or {})