#include "../src/btop_cpu_grid.hpp"
#include <cassert>
#include <iostream>

int main() {
    assert(!Cpu::logical_grid_layout(76, 4, 32));
    assert(Cpu::logical_grid_layout(156, 16, 32));
    assert(!Cpu::logical_grid_layout(0, 20, 32));
    assert(!Cpu::logical_grid_layout(156, 16, 0));
    for (int count : {1, 2, 8, 32, 128, 1024}) {
        for (int width : {12, 60, 80, 156, 196, 400, 1000}) {
            for (int height : {4, 8, 16, 25, 60, 120}) {
                const auto grid = Cpu::logical_grid_layout(width, height, count);
                if (!grid) continue;
                assert(grid.columns * grid.rows >= count);
                assert(grid.columns * (grid.cell_width + 1) - 1 <= width);
                assert(grid.rows * (grid.cell_height + 1) - 1 <= height);
                assert(grid.cell_height - 3 >= 1);
                assert(grid.cell_width - 2 >= 8 + (int)std::to_string(count - 1).size());
            }
        }
    }
    std::cout << "Grid fit, fallback, label widths and bounds passed for 1–1024 processors\n";
}
