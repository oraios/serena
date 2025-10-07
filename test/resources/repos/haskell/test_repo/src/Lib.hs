module Lib
  ( hello
  , add
  , safeDiv
  , Calculator(..)
  , Operation(..)
  , validateUser
  , User(..)
  , processUsers
  , chainOperations
  , combineResults
  , allPairs
  , calculateSafely
  , Maybe(..)
  , Either(..)
  ) where

import Control.Applicative (liftA2)
import Control.Monad (join)

-- Basic functions
hello :: String
hello = "Hello, Haskell!"

add :: Int -> Int -> Int
add x y = x + y

-- Safe division with Maybe monad
safeDiv :: Int -> Int -> Maybe Int
safeDiv _ 0 = Nothing
safeDiv x y = Just (x `div` y)

-- Error handling with Either
safeDivEither :: Int -> Int -> Either String Int
safeDivEither _ 0 = Left "Division by zero"
safeDivEither x y = Right (x `div` y)

-- | A calculator with configurable precision.
-- This data type represents a calculator instance with an identifier and precision setting.
data Calculator = Calculator
  { calcId :: String      -- ^ Unique identifier for the calculator
  , precision :: Int      -- ^ Number of decimal places for calculations
  } deriving (Show, Eq)

-- | Operations that can be performed by the calculator
data Operation 
  = Add Int Int           -- ^ Addition operation
  | Multiply Int Int      -- ^ Multiplication operation
  | Divide Int Int        -- ^ Division operation
  deriving (Show, Eq)

-- | Represents a user in the system with validation support.
-- Users must have valid IDs, names, and non-negative ages.
data User = User
  { userId :: String      -- ^ Unique user identifier
  , userName :: String    -- ^ User's display name
  , userAge :: Int        -- ^ User's age (must be non-negative)
  } deriving (Show, Eq)

-- | Validates user data and returns a User if all fields are valid.
-- Returns Nothing if any validation fails.
validateUser :: String -> String -> Int -> Maybe User
validateUser uid name age
  | null uid = Nothing
  | null name = Nothing
  | age < 0 = Nothing
  | otherwise = Just (User uid name age)

-- Monadic operations
processUsers :: [String] -> [String] -> [Int] -> [Maybe User]
processUsers ids names ages = zipWith3 validateUser ids names ages

-- Functor, Applicative, and Monad examples
chainOperations :: Int -> Maybe Int
chainOperations x = do
  result1 <- safeDiv x 2
  result2 <- safeDiv result1 3
  safeDiv result2 1

-- Applicative functor example
combineResults :: Maybe Int -> Maybe Int -> Maybe Int
combineResults = liftA2 (+)

-- Advanced: Working with nested Monads
nestedMaybe :: Maybe (Maybe Int) -> Maybe Int
nestedMaybe = join

-- List monad for non-deterministic computation
allPairs :: [Int] -> [Int] -> [(Int, Int)]
allPairs xs ys = do
  x <- xs
  y <- ys
  return (x, y)

-- Either monad for error propagation
calculateSafely :: Int -> Int -> Int -> Either String Int
calculateSafely x y z = do
  step1 <- safeDivEither x y
  step2 <- safeDivEither step1 z
  return (step2 + 10)
