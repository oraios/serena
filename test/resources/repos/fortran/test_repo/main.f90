program test_program
    use math_utils
    implicit none
    real :: result
    
    ! Test addition
    result = add_numbers(5.0, 3.0)
    call print_result(result)
    
    ! Test multiplication
    result = multiply_numbers(4.0, 2.0)
    call print_result(result)
    
    print *, "All tests completed"
end program test_program

