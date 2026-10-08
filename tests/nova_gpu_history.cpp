#include "../src/btop_gpu_history.hpp"
#include <cassert>
#include <iostream>
int main() {
    using namespace GpuHistory;
    std::deque<Sample> samples{{{0, 100, 50, -1}, 1000}, {{100, 0, -1, 25}, 1500}, {{50, 50, 50, 50}, 2000}};
    for (int w = 1; w <= 300; ++w) for (int h = 1; h <= 60; ++h) {
        const auto cells = raster(samples, w, h);
        assert(cells.size() == static_cast<size_t>(w*h));
        for (const auto& cell : cells) assert(cell.series <= 15 && bool(cell.series) == bool(cell.dots));
    }
    // Check all eight Braille bit positions, including exact 0% and 100%.
    for (const auto& [value, left, right] : std::array<std::array<int, 3>, 4>{{{100,1,8}, {67,2,16}, {33,4,32}, {0,64,128}}}) {
        const auto cells = raster({{{value, -1, -1, -1}, 0}}, 1, 1);
        assert(cells[0].dots == right && cells[0].series == 1);
        const auto both = raster({{{value, -1, -1, -1}, 0}, {{value, -1, -1, -1}, 1}}, 1, 1);
        assert(both[0].dots == (left | right));
    }
    const auto overlap = raster({{{50,50,50,50}, 0}}, 5, 5);
    assert(overlap[2*5+4].series == 15 && overlap[2*5+4].dots == 32);
    // Close readings previously occupied the same entire character row.
    const auto fine = raster({{{9,-1,-1,-1}, 0}, {{14,-1,-1,-1}, 1}}, 1, 5);
    assert(fine[4].dots == (2 | 8)); // two different vertical levels, connected
    const auto missing = raster({{{0,-1,-1,-1}, 0}, {{-1,-1,-1,-1}, 1}, {{100,-1,-1,-1}, 2}}, 2, 5);
    assert(missing[4*2].dots == 128 && missing[1].dots == 8);
    for (int row = 1; row < 4; ++row) assert(missing[row*2].dots == 0 && missing[row*2+1].dots == 0);
    // Unknown points are gaps, and old samples scroll off at two per column.
    assert(visible_samples(1000, 13) == 26 && visible_samples(1000, 13, false) == 13);
    assert(visible_samples(3, 13) == 3 && visible_samples(10, 0) == 0);
    const auto clipped = raster({{{100,-1,-1,-1},0}, {{0,-1,-1,-1},1}, {{0,-1,-1,-1},2}}, 1, 3);
    assert(clipped[0].series == 0 && clipped[2].dots == (64 | 128));
    const auto ascii = raster({{{50,-1,-1,-1},0}}, 4, 5, false);
    assert(ascii[2*4+3].series == 1 && ascii[2*4+3].dots == 1);
    assert(raster(samples, 0, 3).empty());
    assert(raster({}, 4, 3).size() == 12);
    for (int height = 11; height < 200; ++height) {
        const auto reserved = process_rows(height, 9, true);
        assert(reserved <= 9 && height - reserved >= 11);
        assert(process_rows(height, 9, false) == 0);
    }
    std::cout << "GPU Braille bit mapping, finer vertical/horizontal resolution, axes, unknown gaps, overlaps, ASCII and process-space bounds passed\n";
}
