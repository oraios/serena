process GREET {
    tag "$name"

    input:
    val name

    output:
    path "greeting.txt"

    script:
    """
    echo "Hello, ${name}!" > greeting.txt
    """
}

process SHOUT {
    input:
    path greeting

    output:
    path "shout.txt"

    script:
    """
    tr '[:lower:]' '[:upper:]' < ${greeting} > shout.txt
    """
}
