#include "../src/btop_nova_layout.hpp"
#include "../src/btop_mounts.hpp"
#include <cassert>
#include <iostream>

int main() {
	for (int height = 1; height <= 300; ++height) {
		const auto compact = NovaLayout::cpu_height(height);
		assert(compact >= std::min(8, height) and compact <= height);
	}
	assert(NovaLayout::gpu_height(24, 87, 17, 1, 29) == 27);
	assert(NovaLayout::gpu_height(24, 71, 17, 1, 29) == 25);
	assert(NovaLayout::gpu_height(24, 70, 17, 1, 29) == 24);
	assert(NovaLayout::gpu_height(24, 87, 17, 0, 29) == 24);
	for (int total = 24; total < 200; ++total) for (int count : {1,2,3,6}) {
		const int extra = NovaLayout::gpu_height(11, total, 17, count, 29) - 11;
		assert(extra >= 0 && extra <= 3);
		assert(extra == 0 || total - 17 - (11 + extra) * count >= 29);
	}
	assert(NovaLayout::cpu_height(21) == 14);
	assert(NovaLayout::focus_cpu_height(100, 28, 17, 29) == 17);
	assert(NovaLayout::focus_cpu_height(60, 12, 17, 29) == 17);
	assert(NovaLayout::focus_cpu_height(50, 14, 17, 29) == 0);
	for (int total = 24; total <= 300; ++total)
		for (int gpu : {0, 11, 20, 28, 50})
			for (int body : {22, 29, 40, 80}) {
				for (int minimum : {8, 17, 30, 70}) {
					const int cpu = NovaLayout::focus_cpu_height(total, gpu, minimum, body);
					assert(cpu == (total - gpu - body >= minimum ? minimum : 0));
					assert(cpu == 0 or cpu + gpu + body <= total);
				}
			}
	assert(NovaLayout::memory_height(34, 49, 14, 6, false) == 23);
	assert(NovaLayout::memory_height(34, 49, 14, 6, true) == 34);
	for (int available = 16; available <= 150; ++available)
		for (int previous = 10; previous <= available; ++previous) {
			const auto memory = NovaLayout::memory_height(previous, available, 14, 6, false);
			assert(memory >= std::min(14, available - 6));
			assert(available - memory >= 6);
		}
	for (int height = 16; height <= 150; ++height)
		for (int count : {0, 1, 5, 50, 1000})
			for (bool detailed : {false, true}) {
				const auto table = Mounts::full_table_height(height, 146, count, detailed, true, 16);
				assert(table == 0 or (table >= 5 and height - table >= 16));
				assert(table == 0 or height - table - (detailed ? 8 : 0) >= 13);
			}
	assert(Mounts::full_table_height(58, 200, 5, false, true, 16) == 9);
	assert(Mounts::full_table_height(16, 80, 5, false, true, 16) == 0);
	assert(Mounts::full_table_height(58, 200, 5, false, false, 16) == 0);
	assert(Mounts::columns(144, 17, 33).device >= 33);
	assert(Mounts::columns(198, 17, 90).device >= 90);
	for (int width = 42; width <= 300; ++width) {
		const auto cols = Mounts::columns(width, 17, 33, true);
		assert(cols.total() == width);
		assert(cols.mount >= 14 and (cols.bar == 0 or cols.bar >= 4));
	}
	assert(Mounts::columns(144, 17, 33, true).device == 33);
	assert(Mounts::columns(198, 17, 33, true).mount == 17);
	std::cout << "Compact CPU, memory/network budgets and full-width mount bounds passed\n";
}
