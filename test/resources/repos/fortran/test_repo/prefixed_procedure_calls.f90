program prefixed_procedure_calls
    use prefixed_procedures
    implicit none
    integer :: count
    real(kind=8) :: scaled
    real :: squared

    count = 1
    call increment(count)
    scaled = scale(2.0_8)
    count = double_integer(count)
    count = factorial(count)
    squared = square(2.0)
end program prefixed_procedure_calls
