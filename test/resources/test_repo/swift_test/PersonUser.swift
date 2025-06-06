import Foundation

// Function that uses Person struct and its methods
func processPerson(person: Person) -> String {
    let greeting = person.greet()
    let info = person.formatInfo()
    
    return "\(greeting)\n\(info)"
}

// Create a custom manager
class CustomPersonManager: PersonManager {
    // Override the printAllPeople method
    override func printAllPeople() {
        print("Custom manager printing people:")
        super.printAllPeople()
    }
    
    // Add a new method that uses formatInfo
    func summarizePeople() -> String {
        var summary = ""
        for person in people {
            summary += person.formatInfo() + "\n"
        }
        return summary
    }
}
