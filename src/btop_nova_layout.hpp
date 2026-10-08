/* Copyright 2026. Licensed under the Apache License, Version 2.0. */
#pragma once
#include "btop_cpu_grid.hpp"

namespace NovaLayout {

// Transfer unused aggregate-CPU height to GPU histories, keeping the combined
// budget unchanged. A grid that already fits must continue to fit.
inline int cpu_height(int previous, int width, int processors, bool logical, int footer) {
	int result = std::max(8, previous - previous / 3);
	if (logical and Cpu::logical_grid_layout(width - 4, previous - 4 - footer, processors))
		while (result < previous and not Cpu::logical_grid_layout(width - 4, result - 4 - footer, processors)) ++result;
	return std::min(previous, result);
}

inline int memory_height(int previous, int available, int minimum, int network_minimum, bool swap_visible) {
	const int maximum = std::max(1, available - network_minimum);
	minimum = std::min(minimum, maximum);
	const int target = swap_visible ? previous : (previous * 2 + 2) / 3;
	return std::clamp(target, minimum, maximum);
}

}
