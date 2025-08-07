class User
  attr_accessor :id, :name, :email

  def initialize(id, name, email = nil)
    @id = id
    @name = name
    @email = email
  end

  def full_info
    info = "User: #{@name} (ID: #{@id})"
    info += ", Email: #{@email}" if @email
    info
  end

  def to_hash
    {
      id: @id,
      name: @name,
      email: @email
    }
  end

  def self.from_hash(hash)
    new(hash[:id], hash[:name], hash[:email])
  end

  class << self
    def default_user
      new(0, "Guest")
    end
  end
end

class Item
  attr_reader :id, :name, :price

  def initialize(id, name, price)
    @id = id
    @name = name
    @price = price
  end

  def discounted_price(discount_percent)
    @price * (1 - discount_percent / 100.0)
  end

  def description
    "#{@name}: $#{@price}"
  end
end

module ItemHelpers
  def format_price(price)
    "$#{sprintf('%.2f', price)}"
  end

  def calculate_tax(price, tax_rate = 0.08)
    price * tax_rate
  end
end

class Order
  include ItemHelpers

  def initialize
    @items = []
    @total = 0
  end

  def add_item(item, quantity = 1)
    @items << { item: item, quantity: quantity }
    calculate_total
  end

  def total_with_tax
    tax = calculate_tax(@total)
    @total + tax
  end

  private

  def calculate_total
    @total = @items.sum { |entry| entry[:item].price * entry[:quantity] }
  end
end