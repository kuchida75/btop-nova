/* Copyright 2026. Licensed under the Apache License, Version 2.0. */
#pragma once
#include <algorithm>
#include <cmath>
#include <limits>
#include <string>

namespace Cpu {
	struct LogicalGrid {
		int columns{}, rows{}, cell_width{}, cell_height{};
		explicit operator bool() const { return columns > 0; }
	};

	// Cell border + processor label + at least one row of history.
	inline LogicalGrid logical_grid_layout(int width, int height, int count) {
		LogicalGrid best;
		if (width <= 0 or height <= 0 or count <= 0) return best;
		const int minimum_width = std::max(12, 10 + (int)std::to_string(count - 1).size());
		double best_score = std::numeric_limits<double>::max();
		for (int columns = 1; columns <= std::min(count, (width + 1) / (minimum_width + 1)); ++columns) {
			const int rows = (count + columns - 1) / columns;
			const int cell_width = (width - columns + 1) / columns;
			const int cell_height = (height - rows + 1) / rows;
			if (cell_width < minimum_width or cell_height < 4) continue;
			const double score = std::abs(cell_width / (double)cell_height - 2.5)
				+ 4.0 * (columns * rows - count) / count;
			if (score < best_score) {
				best_score = score;
				best = {columns, rows, cell_width, cell_height};
			}
		}
		return best;
	}
}
