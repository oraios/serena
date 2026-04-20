module Main exposing (main, greet, calculateSum)

{-| Main module for testing Elm language server functionality.

This module contains basic functions to test:

  - Symbol discovery
  - Reference finding
  - Cross-file imports

-}

import Browser
import Html exposing (Html, div, h1, p, text)
import Utils exposing (formatMessage, addNumbers)


{-| The main entry point for the application
-}
main : Program () Model Msg
main =
    Browser.sandbox
        { init = init
        , view = view
        , update = update
        }


type alias Model =
    { message : String
    , count : Int
    }


init : Model
init =
    { message = greet "World"
    , count = calculateSum 5 10
    }


type Msg
    = NoOp


update : Msg -> Model -> Model
update msg model =
    case msg of
        NoOp ->
            model


view : Model -> Html Msg
view model =
    div []
        [ h1 [] [ text (formatMessage model.message) ]
        , p [] [ text ("Count: " ++ String.fromInt model.count) ]
        ]


{-| Greet someone by name
-}
greet : String -> String
greet name =
    "Hello, " ++ name ++ "!"


{-| Calculate the sum of two numbers
-}
calculateSum : Int -> Int -> Int
calculateSum a b =
    addNumbers a b
