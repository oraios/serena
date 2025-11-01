module math_utils
    implicit none
    contains
    
    function add_numbers(a, b) result(sum)
        real, intent(in) :: a, b
        real :: sum
        sum = a + b
    end function add_numbers
    
    function multiply_numbers(x, y) result(product)
        real, intent(in) :: x, y
        real :: product
        product = x * y
    end function multiply_numbers
    
    subroutine print_result(value)
        real, intent(in) :: value
        print *, "Result is:", value
    end subroutine print_result
end module math_utils

