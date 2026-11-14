// Open-top box with rounded vertical corners and a partial top cover
length = 115;   // mm
width  = 127;   // mm
height = 40;    // mm
wall   = 2;       // wall and floor thickness
r      = 4;       // outer corner radius (must be greater than wall)

cover_width = 32;    // how far the cover extends inward from the long wall
cover_thick = wall;  // cover thickness, flush with the top

$fn = 64;

// Rounded rectangle extruded to a height
module rounded_box(l, w, h, rad) {
    hull() {
        for (x = [rad, l - rad], y = [rad, w - rad])
            translate([x, y, 0])
                cylinder(r = rad, h = h);
    }
}

union() {
    // the box
    difference() {
        rounded_box(length, width, height, r);

        translate([wall, wall, wall])
            rounded_box(length - 2*wall, width - 2*wall, height, r - wall);
    }

    // partial top cover, trimmed to the rounded outline
    intersection() {
        rounded_box(length, width, height, r);
        translate([0, 0, height - cover_thick])
            cube([length, cover_width, cover_thick]);
    }
}