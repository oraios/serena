<?php

namespace SerenaTest;

/**
 * Interface for objects that can greet.
 */
interface GreeterInterface
{
    public function greet(string $name): string;
}

/**
 * Abstract base class for animals.
 */
abstract class Animal
{
    protected string $name;
    protected int $age;

    public function __construct(string $name, int $age)
    {
        $this->name = $name;
        $this->age  = $age;
    }

    public function getName(): string
    {
        return $this->name;
    }

    public function getAge(): int
    {
        return $this->age;
    }

    abstract public function describe(): string;
}

/**
 * A concrete animal that can greet visitors.
 */
class Dog extends Animal implements GreeterInterface
{
    private string $breed;

    public function __construct(string $name, int $age, string $breed)
    {
        parent::__construct($name, $age);
        $this->breed = $breed;
    }

    public function greet(string $visitorName): string
    {
        return "Woof! I'm {$this->name}. Hello, {$visitorName}!";
    }

    public function getBreed(): string
    {
        return $this->breed;
    }

    public function describe(): string
    {
        return "Dog: {$this->name} ({$this->breed}), age {$this->age}";
    }

    public function fetch(string $item): string
    {
        return "{$this->name} fetches the {$item}!";
    }
}

/**
 * Another concrete animal.
 */
class Cat extends Animal
{
    private bool $indoor;

    public function __construct(string $name, int $age, bool $indoor = true)
    {
        parent::__construct($name, $age);
        $this->indoor = $indoor;
    }

    public function isIndoor(): bool
    {
        return $this->indoor;
    }

    public function describe(): string
    {
        $type = $this->indoor ? 'indoor' : 'outdoor';
        return "Cat: {$this->name} ({$type}), age {$this->age}";
    }
}

const MAX_ANIMALS = 100;
const DEFAULT_BREED = 'Mixed';

/**
 * Factory function to create an animal by type name.
 */
function createAnimal(string $type, string $name, int $age): Animal
{
    return match ($type) {
        'dog' => new Dog($name, $age, DEFAULT_BREED),
        'cat' => new Cat($name, $age),
        default => throw new \InvalidArgumentException("Unknown animal type: {$type}"),
    };
}

/**
 * Returns a summary string for a list of animals.
 *
 * @param Animal[] $animals
 */
function summarizeAnimals(array $animals): string
{
    return implode(', ', array_map(fn(Animal $a) => $a->describe(), $animals));
}
