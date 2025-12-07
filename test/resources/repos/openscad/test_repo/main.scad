// Main file demonstrating OpenSCAD features

use <shapes.scad>
use <utils.scad>

// Local variable
model_scale = 1.5;

// Using modules from shapes.scad
cube_shape(15);

translate([25, 0, 0]) {
    sphere_shape(8);
}

translate([0, 25, 0]) {
    cylinder_shape(height = 15, radius = 6);
}

// Using combined shape
translate([25, 25, 0]) {
    combined_shape(12, 6);
}

// Using utilities
translate([0, 50, 0]) {
    hollow_box(20);
}

// Using function from utils
box_vol = box_volume(10, 10, 10);
echo("Box volume:", box_vol);

// Local module definition
module local_assembly() {
    cube_shape(model_scale * 10);
    translate([20, 0, 0]) {
        sphere_shape(model_scale * 5);
    }
}

// Using local module
translate([50, 0, 0]) {
    local_assembly();
}
