/// Data models for the test application
library models;

/// Represents a user in the system
class User {
  /// User's unique identifier
  final int id;
  
  /// User's name
  final String name;
  
  /// User's email address
  final String email;
  
  /// User's age
  int _age;

  /// Constructor for creating a User
  User(this.id, this.name, this.email, this._age);

  /// Named constructor for creating a user with default values
  User.withDefaults(this.id, this.name) 
    : email = '$name@example.com',
      _age = 0;

  /// Getter for user's age
  int get age => _age;

  /// Setter for user's age with validation
  set age(int value) {
    if (value < 0 || value > 150) {
      throw ArgumentError('Age must be between 0 and 150');
    }
    _age = value;
  }

  /// Checks if the user is an adult
  bool get isAdult => _age >= 18;

  /// Returns a string representation of the user
  @override
  String toString() {
    return 'User(id: $id, name: $name, email: $email, age: $_age)';
  }

  /// Checks equality based on user ID
  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is User && other.id == id;
  }

  @override
  int get hashCode => id.hashCode;
}

/// Represents a product in an e-commerce system
class Product {
  final String id;
  final String name;
  final double price;
  final String category;
  int _stock;

  Product(this.id, this.name, this.price, this.category, this._stock);

  /// Getter for current stock
  int get stock => _stock;

  /// Reduces stock by the specified amount
  bool reduceStock(int amount) {
    if (amount <= 0) {
      throw ArgumentError('Amount must be positive');
    }
    if (_stock >= amount) {
      _stock -= amount;
      return true;
    }
    return false;
  }

  /// Increases stock by the specified amount
  void increaseStock(int amount) {
    if (amount <= 0) {
      throw ArgumentError('Amount must be positive');
    }
    _stock += amount;
  }

  /// Checks if the product is in stock
  bool get isInStock => _stock > 0;

  /// Calculates the total value of stock
  double get totalStockValue => _stock * price;
}

/// An abstract base class for different types of accounts
abstract class Account {
  final String accountNumber;
  double _balance;

  Account(this.accountNumber, this._balance);

  double get balance => _balance;

  /// Abstract method that must be implemented by subclasses
  bool withdraw(double amount);

  /// Deposits money into the account
  void deposit(double amount) {
    if (amount <= 0) {
      throw ArgumentError('Deposit amount must be positive');
    }
    _balance += amount;
  }
}

/// A savings account implementation
class SavingsAccount extends Account {
  final double interestRate;

  SavingsAccount(super.accountNumber, super.balance, this.interestRate);

  @override
  bool withdraw(double amount) {
    if (amount <= 0) {
      throw ArgumentError('Withdrawal amount must be positive');
    }
    if (_balance >= amount) {
      _balance -= amount;
      return true;
    }
    return false;
  }

  /// Applies interest to the account balance
  void applyInterest() {
    _balance += _balance * interestRate / 100;
  }
}

/// Generic container class demonstrating type parameters
class Container<T> {
  final List<T> _items = [];

  /// Adds an item to the container
  void add(T item) {
    _items.add(item);
  }

  /// Removes an item from the container
  bool remove(T item) {
    return _items.remove(item);
  }

  /// Gets all items in the container
  List<T> get items => List.unmodifiable(_items);

  /// Gets the number of items
  int get length => _items.length;

  /// Checks if the container is empty
  bool get isEmpty => _items.isEmpty;

  /// Finds the first item matching the predicate
  T? find(bool Function(T) predicate) {
    for (final item in _items) {
      if (predicate(item)) {
        return item;
      }
    }
    return null;
  }
}