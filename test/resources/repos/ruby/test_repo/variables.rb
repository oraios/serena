require './models.rb'

# Global variables for testing references
$global_counter = 0
$global_config = {
  debug: true,
  timeout: 30
}

class DataContainer
  attr_accessor :status, :data, :metadata

  def initialize
    @status = "pending"
    @data = {}
    @metadata = {
      created_at: Time.now,
      version: "1.0"
    }
  end

  def update_status(new_status)
    old_status = @status
    @status = new_status
    log_status_change(old_status, new_status)
  end

  def process_data(input_data)
    @data = input_data
    @status = "processing"
    
    # Process the data
    result = @data.transform_values { |v| v.to_s.upcase }
    @status = "completed"
    
    result
  end

  def get_metadata_info
    info = "Status: #{@status}, Version: #{@metadata[:version]}"
    info += ", Created: #{@metadata[:created_at]}"
    info
  end

  private

  def log_status_change(old_status, new_status)
    puts "Status changed from #{old_status} to #{new_status}"
  end
end

class StatusTracker
  def initialize
    @tracked_items = []
  end

  def add_item(item)
    @tracked_items << item
    item.status = "tracked" if item.respond_to?(:status=)
  end

  def find_by_status(target_status)
    @tracked_items.select { |item| item.status == target_status }
  end

  def update_all_status(new_status)
    @tracked_items.each do |item|
      item.status = new_status if item.respond_to?(:status=)
    end
  end
end

# Module level variables and functions
module ProcessingHelper
  PROCESSING_MODES = ["sync", "async", "batch"].freeze
  
  @@instance_count = 0
  
  def self.create_processor(mode = "sync")
    @@instance_count += 1
    {
      id: @@instance_count,
      mode: mode,
      created_at: Time.now
    }
  end
  
  def self.get_instance_count
    @@instance_count
  end
end

# Test instances for reference testing
dataclass_instance = DataContainer.new
dataclass_instance.status = "initialized"

second_dataclass = DataContainer.new  
second_dataclass.update_status("ready")

tracker = StatusTracker.new
tracker.add_item(dataclass_instance)
tracker.add_item(second_dataclass)

# Function that uses the variables
def demonstrate_variable_usage
  puts "Global counter: #{$global_counter}"
  
  container = DataContainer.new
  container.status = "demo"
  
  processor = ProcessingHelper.create_processor("async")
  puts "Created processor #{processor[:id]} in #{processor[:mode]} mode"
  
  container
end

# More complex variable interactions
class VariableInteractionTest
  def initialize
    @internal_status = "created"
    @data_containers = []
  end
  
  def add_container(container)
    @data_containers << container
    container.status = "added_to_collection"
    @internal_status = "modified"
  end
  
  def process_all_containers
    @data_containers.each do |container|
      container.status = "batch_processed"
    end
    @internal_status = "processing_complete"
  end
  
  def get_status_summary
    statuses = @data_containers.map(&:status)
    {
      internal: @internal_status,
      containers: statuses,
      count: @data_containers.length
    }
  end
end

# Create instances for testing
interaction_test = VariableInteractionTest.new
interaction_test.add_container(dataclass_instance)
interaction_test.add_container(second_dataclass)