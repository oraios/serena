local module = require("./module")

export type Config = {
    name: string,
    value: number,
    enabled: boolean,
}

local function createConfig(name: string, value: number): Config
    return {
        name = name,
        value = value,
        enabled = true,
    }
end

local function main()
    local config = createConfig("test", 42)
    local result = module.process(config)
    print(result)
end

return {
    createConfig = createConfig,
    main = main,
}