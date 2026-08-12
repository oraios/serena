def normalizeName(String name) {
    return name.trim().toLowerCase()
}

def buildGreeting(String name) {
    return "Hello, " + normalizeName(name)
}
