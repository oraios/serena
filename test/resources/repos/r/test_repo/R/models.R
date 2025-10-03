#' Fit a linear model
#'
#' @param formula A formula for the model
#' @param data A data frame containing the variables
#' @return A fitted lm object
#' @export
fit_linear_model <- function(formula, data) {
    if (missing(formula) || missing(data)) {
        stop("Both formula and data are required")
    }
    
    model <- lm(formula, data = data)
    
    # Add some custom attributes
    attr(model, "created_by") <- "fit_linear_model"
    attr(model, "creation_time") <- Sys.time()
    
    return(model)
}

#' Plot data using ggplot2-style syntax
#'
#' @param data A data frame
#' @param x_var Column name for x-axis
#' @param y_var Column name for y-axis
#' @return A plot object
#' @export
plot_data <- function(data, x_var, y_var) {
    if (!is.data.frame(data)) {
        stop("data must be a data frame")
    }
    
    if (!(x_var %in% names(data))) {
        stop(paste("Column", x_var, "not found in data"))
    }
    
    if (!(y_var %in% names(data))) {
        stop(paste("Column", y_var, "not found in data"))
    }
    
    # Create a simple base R plot
    plot(data[[x_var]], data[[y_var]], 
         xlab = x_var, ylab = y_var,
         main = paste(y_var, "vs", x_var))
    
    # Add a trend line
    abline(lm(data[[y_var]] ~ data[[x_var]]), col = "red")
}