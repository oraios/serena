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

-- Data types and algebraic data types
data Calculator = Calculator
  { calcId :: String
  , precision :: Int
  } deriving (Show, Eq)

data Operation 
  = Add Int Int
  | Multiply Int Int
  | Divide Int Int
  deriving (Show, Eq)

-- User validation with Maybe
data User = User
  { userId :: String
  , userName :: String  
  , userAge :: Int
  } deriving (Show, Eq)

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
