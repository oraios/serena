# Example R script demonstrating package usage

# Load required libraries
library(testpackage)

# Create sample data
sample_data <- create_data_frame(n = 50)

# Process the data
clean_data <- process_data(sample_data)

# Calculate some statistics
mean_value <- calculate_mean(clean_data$value)
cat("Mean value:", mean_value, "\n")

# Fit a simple model
model <- fit_linear_model(value ~ id, data = clean_data)
summary(model)

# Create a plot
plot_data(clean_data, "id", "value")

# Additional analysis function (not exported)
analyze_categories <- function(data) {
    table(data$category)
}

# Run the analysis
category_summary <- analyze_categories(clean_data)
print(category_summary)