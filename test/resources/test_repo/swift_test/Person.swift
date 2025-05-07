import Foundation

// Define a simple struct for a person
struct Person {
    var name: String
    var age: Int
    
    // Method to greet
    func greet() -> String {
        return "Hello, my name is \(name) and I am \(age) years old."
    }
    
    // Static function to create a person
    static func createPerson(name: String, age: Int) -> Person {
        return Person(name: name, age: age)
    }
}

// Extension to add additional functionality
extension Person {
    // Calculate if the person is an adult
    func isAdult() -> Bool {
        return age >= 18
    }
    
    // Format the person's information
    func formatInfo() -> String {
        let adultStatus = isAdult() ? "an adult" : "not an adult"
        return "\(name) is \(age) years old and is \(adultStatus)."
    }
}

// A class that uses Person
class PersonManager {
    var people: [Person] = []
    
    // Add a person to the list
    func addPerson(person: Person) {
        people.append(person)
    }
    
    // Get all adults
    func getAdults() -> [Person] {
        return people.filter { $0.isAdult() }
    }
    
    // Print information about all people
    func printAllPeople() {
        for person in people {
            print(person.formatInfo())
        }
    }
}
