import Foundation

// Import Person and PersonUser types
@_exported import TestSwiftModule

// Main program
func main() {
    // Create some instances
    let john = Person(name: "John", age: 25)
    let alice = Person.createPerson(name: "Alice", age: 17)
    
    // Use the PersonManager
    let manager = PersonManager()
    manager.addPerson(person: john)
    manager.addPerson(person: alice)
    
    // Print some information
    print(john.greet())
    print(alice.formatInfo())
    
    // Get all adults
    let adults = manager.getAdults()
    print("Number of adults: \(adults.count)")
    
    // Create a new person
    let sarah = Person(name: "Sarah", age: 30)
    
    // Test the isAdult method
    if sarah.isAdult() {
        print("\(sarah.name) is an adult")
    }
    
    // Use the custom manager
    let customManager = CustomPersonManager()
    customManager.addPerson(person: sarah)
    customManager.addPerson(person: Person(name: "Mike", age: 15))
    
    // Print all people using the custom manager
    customManager.printAllPeople()
    
    // Test the processPerson function
    let result = processPerson(person: sarah)
    print(result)
}

// Run the main function
main()