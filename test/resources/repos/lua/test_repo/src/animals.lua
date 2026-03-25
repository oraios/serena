---@class Animal
local Animal = {}
Animal.__index = Animal

---@param name string
---@return Animal
function Animal:new(name)
    local self = setmetatable({}, Animal)
    self.name = name
    return self
end

---@return string
function Animal:speak()
    return self.name .. " makes a sound"
end

---@class Dog: Animal
local Dog = setmetatable({}, { __index = Animal })
Dog.__index = Dog

---@param name string
---@return Dog
function Dog:new(name)
    local self = Animal.new(self, name)
    return setmetatable(self, Dog)
end

---@return string
function Dog:speak()
    return self.name .. " says woof"
end

return {
    Animal = Animal,
    Dog = Dog,
}
