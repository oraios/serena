module Formatter

type IGreeter =
    abstract member FormatGreeting: string -> string

type ConsoleGreeter() =
    interface IGreeter with
        member _.FormatGreeting(name: string) = sprintf "Hello, %s!" name
