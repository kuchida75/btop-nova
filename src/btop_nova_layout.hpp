/* Copyright 2026. Licensed under the Apache License, Version 2.0. */
#pragma once
#include <algorithm>

namespace NovaLayout {

// Transfer unused aggregate-CPU height to GPU histories, keeping the combined
// budget unchanged.
inline int cpu_height(int previous) {
	return std::min(previous, std::max(8, previous - previous / 3));
}

inline int memory_height(int previous, int available, int minimum, int network_minimum, bool swap_visible) {
	const int maximum = std::max(1, available - network_minimum);
	minimum = std::min(minimum, maximum);
	const int target = swap_visible ? previous : (previous * 2 + 2) / 3;
	return std::clamp(target, minimum, maximum);
}

}
