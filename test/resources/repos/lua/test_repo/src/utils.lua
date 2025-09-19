-- utils.lua: Utility functions for the test repository

local utils = {}

-- String utilities
function utils.trim(s)
    return s:match("^%s*(.-)%s*$")
end

function utils.split(str, delimiter)
    local result = {}
    local pattern = string.format("([^%s]+)", delimiter)
    for match in string.gmatch(str, pattern) do
        table.insert(result, match)
    end
    return result
end

function utils.starts_with(str, prefix)
    return str:sub(1, #prefix) == prefix
end

function utils.ends_with(str, suffix)
    return str:sub(-#suffix) == suffix
end

-- Table utilities
function utils.deep_copy(orig)
    local orig_type = type(orig)
    local copy
    if orig_type == 'table' then
        copy = {}
        for orig_key, orig_value in next, orig, nil do
            copy[utils.deep_copy(orig_key)] = utils.deep_copy(orig_value)
        end
        setmetatable(copy, utils.deep_copy(getmetatable(orig)))
    else
        copy = orig
    end
    return copy
end

function utils.table_contains(tbl, value)
    for _, v in ipairs(tbl) do
        if v == value then
            return true
        end
    end
    return false
end

function utils.table_merge(t1, t2)
    local result = {}
    for k, v in pairs(t1) do
        result[k] = v
    end
    for k, v in pairs(t2) do
        result[k] = v
    end
    return result
end

-- File utilities
function utils.read_file(path)
    local file = io.open(path, "r")
    if not file then
        return nil, "Could not open file: " .. path
    end
    local content = file:read("*all")
    file:close()
    return content
end

function utils.write_file(path, content)
    local file = io.open(path, "w")
    if not file then
        return false, "Could not open file for writing: " .. path
    end
    file:write(content)
    file:close()
    return true
end

-- Class-like structure
utils.Logger = {}
utils.Logger.__index = utils.Logger

function utils.Logger:new(name)
    local self = setmetatable({}, utils.Logger)
    self.name = name or "default"
    self.level = "info"
    return self
end

function utils.Logger:set_level(level)
    self.level = level
end

function utils.Logger:log(message, level)
    level = level or self.level
    print(string.format("[%s] %s: %s", self.name, level:upper(), message))
end

function utils.Logger:debug(message)
    self:log(message, "debug")
end

function utils.Logger:info(message)
    self:log(message, "info")
end

function utils.Logger:warn(message)
    self:log(message, "warn")
end

function utils.Logger:error(message)
    self:log(message, "error")
end

return utils