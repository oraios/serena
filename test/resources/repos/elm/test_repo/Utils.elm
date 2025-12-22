module Utils exposing (formatMessage, addNumbers, multiplyNumbers)

{-| Utility functions for the Elm test application.

This module provides helper functions used by other modules.

-}


{-| Format a message by adding brackets around it
-}
formatMessage : String -> String
formatMessage msg =
    "[ " ++ msg ++ " ]"


{-| Add two numbers together
-}
addNumbers : Int -> Int -> Int
addNumbers x y =
    x + y


{-| Multiply two numbers
-}
multiplyNumbers : Int -> Int -> Int
multiplyNumbers x y =
    x * y
