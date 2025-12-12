#' Calculate mean of numeric vector
#'
#' @param x A numeric vector
#' @return The mean of the vector
#' @export
calculate_mean <- function(x) {
    if (!is.numeric(x)) {
        stop("Input must be numeric")
    }
    mean(x, na.rm = TRUE)
}

#' Process data by removing missing values
#'
#' @param data A data frame
#' @return A cleaned data frame
#' @export
process_data <- function(data) {
    if (!is.data.frame(data)) {
        stop("Input must be a data frame")
    }
    
    # Remove rows with any missing values
    clean_data <- na.omit(data)
    
    # Add a processed flag
    clean_data$processed <- TRUE
    
    return(clean_data)
}

#' Create a sample data frame
#'
#' @param n Number of rows to create
#' @return A data frame with sample data
#' @export
create_data_frame <- function(n = 100) {
    data.frame(
        id = 1:n,
        value = rnorm(n),
        category = sample(c("A", "B", "C"), n, replace = TRUE),
        stringsAsFactors = FALSE
    )
}