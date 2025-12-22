namespace Models

/// Person record type
type Person = {
    Name: string
    Age: int
    Email: string option
}

module PersonModule =
    /// Create a new person
    let createPerson name age email =
        { Name = name; Age = age; Email = email }
    
    /// Check if person is an adult
    let isAdult person =
        person.Age >= 18
    
    /// Get display name
    let getDisplayName person =
        match person.Email with
        | Some email -> $"{person.Name} ({email})"
        | None -> person.Name
    
    /// Update person age
    let updateAge newAge person =
        { person with Age = newAge }

/// Address type
type Address = {
    Street: string
    City: string
    ZipCode: string
    Country: string
}

/// Employee type that extends Person concept
type Employee = {
    Person: Person
    EmployeeId: int
    Department: string
    Salary: decimal
    Address: Address option
}