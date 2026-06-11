#pragma once

#include "GameFramework/Actor.h"

class APawn : public AActor
{
public:
    virtual void PossessedBy(AActor* NewController) {}
};
