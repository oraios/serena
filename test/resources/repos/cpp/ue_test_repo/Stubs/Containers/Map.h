// Minimal TMap stand-in: just enough surface for the fixture sources to parse.
#pragma once

template <typename KeyType, typename ValueType>
class TMap
{
public:
    ValueType& Add(const KeyType& Key, const ValueType& Value) { static ValueType V; return V; }
    ValueType* Find(const KeyType& Key) { return nullptr; }
    bool Contains(const KeyType& Key) const { return false; }
    int Num() const { return 0; }
};
