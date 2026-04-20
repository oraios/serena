module geometry_types
    implicit none

    ! Simple type definition
    type Point2D
        real :: x, y
    end type Point2D

    ! Type with double colon syntax
    type :: Circle
        real :: radius
        type(Point2D) :: center
    end type Circle

    ! Type with extends (inheritance)
    type, extends(Point2D) :: Point3D
        real :: z
    end type Point3D

    ! Named interface
    interface distance
        module procedure distance_2d, distance_3d
    end interface distance

contains

    function distance_2d(p1, p2) result(dist)
        type(Point2D), intent(in) :: p1, p2
        real :: dist
        dist = sqrt((p2%x - p1%x)**2 + (p2%y - p1%y)**2)
    end function distance_2d

    function distance_3d(p1, p2) result(dist)
        type(Point3D), intent(in) :: p1, p2
        real :: dist
        dist = sqrt((p2%x - p1%x)**2 + (p2%y - p1%y)**2 + (p2%z - p1%z)**2)
    end function distance_3d

    function circle_area(c) result(area)
        type(Circle), intent(in) :: c
        real :: area
        real, parameter :: pi = 3.14159265359
        area = pi * c%radius**2
    end function circle_area

end module geometry_types
