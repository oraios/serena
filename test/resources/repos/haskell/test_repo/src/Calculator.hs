module Calculator
    ( Calculator(..)
    , add
    , subtract
    , multiply
    , divide
    , calculate
    ) where

import Prelude hiding (subtract)
import Helper (validateNumber)

-- | A simple calculator data type
data Calculator = Calculator
    { calcName :: String
    , calcVersion :: Int
    } deriving (Show, Eq)

-- | Add two numbers
add :: Int -> Int -> Int
add x y = validateNumber x + validateNumber y

-- | Subtract two numbers
subtract :: Int -> Int -> Int
subtract x y = validateNumber x - validateNumber y

-- | Multiply two numbers
multiply :: Int -> Int -> Int
multiply x y = x * y

-- | Divide two numbers (returns Maybe to handle division by zero)
divide :: Int -> Int -> Maybe Int
divide _ 0 = Nothing
divide x y = Just (x `div` y)

-- | Perform a calculation based on operator
calculate :: Calculator -> String -> Int -> Int -> Maybe Int
calculate calc op x y = case op of
    "add"      -> Just (add x y)
    "subtract" -> Just (subtract x y)
    "multiply" -> Just (multiply x y)
    "divide"   -> divide x y
    _          -> Nothing
