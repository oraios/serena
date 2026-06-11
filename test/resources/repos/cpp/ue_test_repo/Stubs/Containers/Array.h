// Minimal TArray stand-in: just enough surface for the fixture sources to parse.
#pragma once

template <typename ElementType>
class TArray
{
public:
    void Add(const ElementType& Item) {}
    int Num() const { return 0; }
    ElementType* GetData() { return nullptr; }
};
