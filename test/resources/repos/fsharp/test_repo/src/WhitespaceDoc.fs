module TestProject.WhitespaceDoc

/// Doc for SpacedRecord
type SpacedRecord = { X: int }


    /// Doc for TabbedClass
    type TabbedClass() =
        member _.Value = 42

/// Doc for LiteralValue
[<Literal>]
let LiteralValue = 123

/// First line of multi
/// Second line of multi
type MultiLineDoc() =
    member _.Ping() = ()
