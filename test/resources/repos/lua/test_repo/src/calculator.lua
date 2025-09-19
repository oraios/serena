-- calculator.lua: A simple calculator module for testing LSP features

local calculator = {}

-- Basic arithmetic operations
function calculator.add(a, b)
    return a + b
end

function calculator.subtract(a, b)
    return a - b
end

function calculator.multiply(a, b)
    return a * b
end

function calculator.divide(a, b)
    if b == 0 then
        error("Division by zero")
    end
    return a / b
end

-- Advanced operations
function calculator.power(base, exponent)
    return base ^ exponent
end

function calculator.factorial(n)
    if n < 0 then
        error("Factorial is not defined for negative numbers")
    elseif n == 0 or n == 1 then
        return 1
    else
        local result = 1
        for i = 2, n do
            result = result * i
        end
        return result
    end
end

-- Statistics functions
function calculator.mean(numbers)
    if #numbers == 0 then
        return nil
    end
    
    local sum = 0
    for _, num in ipairs(numbers) do
        sum = sum + num
    end
    return sum / #numbers
end

function calculator.median(numbers)
    if #numbers == 0 then
        return nil
    end
    
    local sorted = {}
    for i, v in ipairs(numbers) do
        sorted[i] = v
    end
    table.sort(sorted)
    
    local mid = math.floor(#sorted / 2)
    if #sorted % 2 == 0 then
        return (sorted[mid] + sorted[mid + 1]) / 2
    else
        return sorted[mid + 1]
    end
end

return calculator