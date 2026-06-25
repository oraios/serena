// Minimal TSet stand-in: just enough surface for the fixture sources to parse.
#pragma once

template <typename ElementType>
class TSet
{
public:
    void Add(const ElementType& Item) {}
    bool Contains(const ElementType& Item) const { return false; }
    int Num() const { return 0; }
};
