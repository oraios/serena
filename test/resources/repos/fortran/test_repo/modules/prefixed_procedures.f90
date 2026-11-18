module prefixed_procedures
    implicit none
contains
    pure subroutine increment(value)
        integer, intent(inout) :: value
        value = value + 1
    end subroutine increment

    real(kind=8) function scale(value)
        real(kind=8), intent(in) :: value
        scale = value * 2.0_8
    end function scale

    pure integer(kind=4) function double_integer(value)
        integer(kind=4), intent(in) :: value
        double_integer = value * 2
    end function double_integer

    recursive function factorial(value) result(product)
        integer, intent(in) :: value
        integer :: product
        if (value <= 1) then
            product = 1
        else
            product = value * factorial(value - 1)
        end if
    end function factorial

    elemental real function square(value)
        real, intent(in) :: value
        square = value * value
    end function square
end module prefixed_procedures
