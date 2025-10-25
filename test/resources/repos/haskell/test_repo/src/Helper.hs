module Helper
    ( validateNumber
    , isPositive
    , isNegative
    , absolute
    ) where

-- | Validate that a number is not zero (for demonstration)
validateNumber :: Int -> Int
validateNumber x = if x == 0 then error "Zero not allowed" else x

-- | Check if a number is positive
isPositive :: Int -> Bool
isPositive x = x > 0

-- | Check if a number is negative
isNegative :: Int -> Bool
isNegative x = x < 0

-- | Get absolute value
absolute :: Int -> Int
absolute x = if isNegative x then negate x else x
