// Stub of UE's log category macros (Logging/LogMacros.h). The DECLARE/DEFINE pair
// manufactures a category object symbol; UE_LOG itself expands to nothing relevant.
#pragma once

#define DECLARE_LOG_CATEGORY_EXTERN(CategoryName, DefaultVerbosity, CompileTimeVerbosity) \
    struct FLogCategory##CategoryName \
    { \
    }; \
    extern FLogCategory##CategoryName CategoryName;

#define DEFINE_LOG_CATEGORY(CategoryName) FLogCategory##CategoryName CategoryName;

#define UE_LOG(CategoryName, Verbosity, Format, ...)
