// Shape module definitions

// A simple cube shape with configurable size
module cube_shape(size = 10) {
    cube([size, size, size]);
}

// A sphere shape with configurable radius
module sphere_shape(radius = 5) {
    sphere(r = radius);
}

// A cylinder shape with configurable dimensions
module cylinder_shape(height = 10, radius = 5) {
    cylinder(h = height, r = radius);
}

// Combined shape module
module combined_shape(cube_size = 10, sphere_radius = 5) {
    union() {
        cube_shape(cube_size);
        translate([cube_size + 5, 0, 0]) {
            sphere_shape(sphere_radius);
        }
    }
}
