// Stub of UE's delegate declaration macros (Delegates/DelegateCombinations.h).
// Unlike the empty annotation macros, these manufacture a class at the expansion
// site. The stubs preserve exactly that property for every delegate family:
// single-cast, multicast, events, and the dynamic (reflection-visible) variants.
#pragma once

#define DECLARE_DELEGATE(DelegateName) \
    class DelegateName \
    { \
    public: \
        void Execute() {} \
        bool IsBound() const { return false; } \
    };

#define DECLARE_DELEGATE_OneParam(DelegateName, Param1Type) \
    class DelegateName \
    { \
    public: \
        void Execute(Param1Type) {} \
        bool IsBound() const { return false; } \
    };

#define DECLARE_DELEGATE_RetVal(ReturnType, DelegateName) \
    class DelegateName \
    { \
    public: \
        ReturnType Execute() { return ReturnType(); } \
        bool IsBound() const { return false; } \
    };

#define DECLARE_MULTICAST_DELEGATE(DelegateName) \
    class DelegateName \
    { \
    public: \
        void Broadcast() {} \
    };

#define DECLARE_MULTICAST_DELEGATE_OneParam(DelegateName, Param1Type) \
    class DelegateName \
    { \
    public: \
        void Broadcast(Param1Type) {} \
    };

#define DECLARE_EVENT(OwningType, EventName) \
    class EventName \
    { \
    public: \
        void Broadcast() {} \
    };

#define DECLARE_DYNAMIC_DELEGATE(DelegateName) \
    class DelegateName \
    { \
    public: \
        void ExecuteIfBound() {} \
    };

#define DECLARE_DYNAMIC_MULTICAST_DELEGATE(DelegateName) \
    class DelegateName \
    { \
    public: \
        void Broadcast() {} \
        void AddDynamic(void* Object, void* Func) {} \
    };

#define DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(DelegateName, Param1Type, Param1Name) \
    class DelegateName \
    { \
    public: \
        void Broadcast(Param1Type Param1Name) {} \
        void AddDynamic(void* Object, void* Func) {} \
    };

#define DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(DelegateName, Param1Type, Param1Name, Param2Type, Param2Name) \
    class DelegateName \
    { \
    public: \
        void Broadcast(Param1Type Param1Name, Param2Type Param2Name) {} \
        void AddDynamic(void* Object, void* Func) {} \
    };
