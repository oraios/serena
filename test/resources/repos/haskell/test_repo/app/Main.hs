module Main where

import Lib (hello, add, safeDiv, Calculator(..), Operation(..), validateUser, User(..), 
           processUsers, chainOperations, combineResults, allPairs, calculateSafely)

main :: IO ()
main = do
  putStrLn hello
  print (add 2 3)
  
  -- Safe division examples
  print (safeDiv 10 2)  -- Just 5
  print (safeDiv 10 0)  -- Nothing
  
  -- Calculator data type
  let calc = Calculator "calc-1" 2
  print calc
  
  -- User validation
  let validUser = validateUser "1" "Alice" 25
  let invalidUser = validateUser "" "Bob" 30
  print validUser    -- Just (User "1" "Alice" 25)
  print invalidUser  -- Nothing
  
  -- Process multiple users
  let users = processUsers ["1", "2", ""] ["Alice", "Bob", "Charlie"] [25, 30, -5]
  print users  -- [Just (User ...), Just (User ...), Nothing]
  
  -- Monadic chaining
  print (chainOperations 24)  -- Just 4
  print (chainOperations 5)   -- Nothing (not divisible)
  
  -- Applicative combinators
  print (combineResults (Just 5) (Just 10))  -- Just 15
  print (combineResults (Just 5) Nothing)    -- Nothing
  
  -- List monad
  let pairs = allPairs [1, 2] [3, 4]
  print pairs  -- [(1,3), (1,4), (2,3), (2,4)]
  
  -- Either monad for error handling
  print (calculateSafely 100 5 2)  -- Right 20
  print (calculateSafely 100 0 2)  -- Left "Division by zero"
