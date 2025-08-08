require './lib.rb'
require './models.rb'

module Services
  class UserService
    attr_reader :users

    def initialize
      @users = {}
    end

    def create_user(id, name)
      user = User.new(id, name)
      @users[id] = user
      user
    end

    def get_user(id)
      @users[id]
    end

    def delete_user(id)
      @users.delete(id)
    end

    private

    def validate_user_data(id, name)
      return false if id.nil? || name.nil?
      return false if name.empty?
      true
    end
  end

  class ItemService
    def initialize
      @items = []
    end

    def add_item(item)
      @items << item
    end

    def find_item(id)
      @items.find { |item| item.id == id }
    end
  end
end

# Module-level function
def create_service_container
  {
    user_service: Services::UserService.new,
    item_service: Services::ItemService.new
  }
end

# Variables for testing
user_service_instance = Services::UserService.new
item_service_instance = Services::ItemService.new