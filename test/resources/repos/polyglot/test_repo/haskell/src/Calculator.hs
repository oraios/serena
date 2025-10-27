-- | Haskell Calculator implementation for polyglot testing

module Calculator
    ( Calculator(..)
    , newCalculator
    , add
    , subtract
    , multiply
    , divide
    , reset
    , helperDouble
    , helperSquare
    ) where

import Prelude hiding (subtract, divide)

-- | Calculator data type with current value
data Calculator = Calculator
    { value :: Double
    } deriving (Show, Eq)

-- | Create new calculator with initial value
newCalculator :: Double -> Calculator
newCalculator initialValue = Calculator { value = initialValue }

-- | Add x to current value
add :: Calculator -> Double -> Calculator
add calc x = calc { value = value calc + x }

-- | Subtract x from current value
subtract :: Calculator -> Double -> Calculator
subtract calc x = calc { value = value calc - x }

-- | Multiply current value by x
multiply :: Calculator -> Double -> Calculator
multiply calc x = calc { value = value calc * x }

-- | Divide current value by x
divide :: Calculator -> Double -> Either String Calculator
divide calc 0 = Left "Cannot divide by zero"
divide calc x = Right $ calc { value = value calc / x }

-- | Reset value to zero
reset :: Calculator -> Calculator
reset calc = calc { value = 0 }

-- | Helper function that doubles a number
helperDouble :: Double -> Double
helperDouble x = x * 2

-- | Helper function that squares a number
helperSquare :: Double -> Double
helperSquare x = x * x
