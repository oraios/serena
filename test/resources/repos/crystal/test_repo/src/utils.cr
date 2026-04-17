module Utils
  def self.format_date(time : Time) : String
    time.to_s("%Y-%m-%d")
  end

  def self.calculate_area(radius : Float64) : Float64
    Math::PI * radius * radius
  end
end
