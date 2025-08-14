require '../services.rb'
require '../models.rb'

class UserStats
  attr_reader :user_count, :active_users, :last_updated

  def initialize
    @user_count = 0
    @active_users = 0
    @last_updated = Time.now
  end

  def update_stats(total, active)
    @user_count = total
    @active_users = active
    @last_updated = Time.now
  end

  def activity_ratio
    return 0.0 if @user_count == 0
    (@active_users.to_f / @user_count * 100).round(2)
  end

  def formatted_stats
    "Users: #{@user_count}, Active: #{@active_users} (#{activity_ratio}%)"
  end
end

class UserManager
  def initialize
    @service = Services::UserService.new
    @stats = UserStats.new
  end

  def create_user_with_tracking(id, name, email = nil)
    user = @service.create_user(id, name)
    user.email = email if email
    
    update_statistics
    notify_user_created(user)
    
    user
  end

  def get_user_details(id)
    user = @service.get_user(id)
    return nil unless user
    
    {
      user_info: user.full_info,
      created_at: Time.now,
      stats: @stats.formatted_stats
    }
  end

  def bulk_create_users(user_data_list)
    created_users = []
    
    user_data_list.each do |data|
      user = create_user_with_tracking(data[:id], data[:name], data[:email])
      created_users << user
    end
    
    created_users
  end

  private

  def update_statistics
    total_users = @service.users.length
    # For demo purposes, assume all users are active
    @stats.update_stats(total_users, total_users)
  end

  def notify_user_created(user)
    puts "User created: #{user.name} (ID: #{user.id})"
  end
end

def process_user_data(raw_data)
  processed = raw_data.map do |entry|
    {
      id: entry["id"] || entry[:id],
      name: entry["name"] || entry[:name],
      email: entry["email"] || entry[:email]
    }
  end
  
  processed.reject { |entry| entry[:name].nil? || entry[:name].empty? }
end

def main
  # Example usage
  manager = UserManager.new
  
  sample_data = [
    { id: 1, name: "Alice Johnson", email: "alice@example.com" },
    { id: 2, name: "Bob Smith", email: "bob@example.com" },
    { id: 3, name: "Charlie Brown" }
  ]
  
  users = manager.bulk_create_users(sample_data)
  
  users.each do |user|
    details = manager.get_user_details(user.id)
    puts details[:user_info]
  end
  
  puts "\nFinal statistics:"
  stats = UserStats.new
  stats.update_stats(users.length, users.length)
  puts stats.formatted_stats
end

# Execute if this file is run directly
main if __FILE__ == $0