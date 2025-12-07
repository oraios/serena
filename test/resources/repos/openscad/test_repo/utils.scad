// Utility functions and constants

// Global constants
wall_thickness = 2;
default_height = 20;

// Helper function to calculate volume of a box
function box_volume(length, width, height) = length * width * height;

// Helper function to calculate area
function calculate_area(length, width) = length * width;

// Module to create a hollow box
module hollow_box(outer_size, wall = wall_thickness) {
    difference() {
        cube([outer_size, outer_size, outer_size]);
        translate([wall, wall, wall]) {
            cube([outer_size - 2*wall, outer_size - 2*wall, outer_size - 2*wall + 1]);
        }
    }
}
