local function process(data: { name: string, value: number }): string
    return `Processing {data.name} with value {data.value}`
end

local function helper(x: number, y: number): number
    return x + y
end

return {
    process = process,
    helper = helper,
}