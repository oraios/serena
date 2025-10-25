module Main (main) where

import Calculator
import Helper

main :: IO ()
main = do
    let calc = Calculator "TestCalc" 1
    putStrLn $ "Using " ++ calcName calc ++ " version " ++ show (calcVersion calc)

    -- Test add function (cross-file reference)
    let result1 = add 5 3
    putStrLn $ "5 + 3 = " ++ show result1

    -- Test subtract (uses validateNumber from Helper)
    let result2 = Calculator.subtract 10 4
    putStrLn $ "10 - 4 = " ++ show result2

    -- Test calculate function
    case calculate calc "multiply" 6 7 of
        Just result -> putStrLn $ "6 * 7 = " ++ show result
        Nothing -> putStrLn "Calculation failed"

    -- Test helper functions directly
    putStrLn $ "Is 5 positive? " ++ show (isPositive 5)
    putStrLn $ "Absolute of -10: " ++ show (absolute (-10))
