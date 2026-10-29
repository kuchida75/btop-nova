// Nova GPU chart geometry. Series: load, allocated VRAM, graphics clock, memory clock, power.
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <deque>
#include <vector>

namespace GpuHistory {
struct Sample {
	std::array<long long, 5> values{-1, -1, -1, -1, -1};
	uint64_t timestamp{}; // steady-clock milliseconds
	long long milliwatts = -1; // Raw power; normalize only when rendering the visible scale.
};
struct Cell {
	unsigned char series{}; // bitmask; zero means background
	unsigned char dots{}; // Unicode Braille's eight-dot mask
};
inline int visible_samples(size_t size, int width, bool braille = true) {
	return width <= 0 ? 0 : static_cast<int>(std::min(size, static_cast<size_t>(width) * (braille ? 2 : 1)));
}
// Two samples and four vertical dots per cell; ASCII uses one point per cell.
// Newest samples stay at the right. Missing readings break the curve.
inline std::vector<Cell> raster(const std::deque<Sample>& samples, int width, int height, bool braille = true) {
	if (width <= 0 or height <= 0) return {};
	std::vector<Cell> result(static_cast<size_t>(width) * height);
	const int columns = width * (braille ? 2 : 1), rows = height * (braille ? 4 : 1);
	const int count = visible_samples(samples.size(), width, braille);
	const int first = static_cast<int>(samples.size()) - count;
	const int offset = columns - count;
	constexpr unsigned char bits[2][4]{{1, 2, 4, 64}, {8, 16, 32, 128}};
	const auto point = [&](int x, int y, int series) {
		auto& cell = result[(braille ? y / 4 : y) * width + (braille ? x / 2 : x)];
		cell.series |= 1 << series;
		cell.dots |= braille ? bits[x % 2][y % 4] : 1;
	};
	for (int series = 4; series >= 0; --series) {
		int previous = -1;
		for (int col = 0; col < count; ++col) {
			const auto value = samples[first + col].values[series];
			if (value < 0) { previous = -1; continue; }
			const int row = ((100 - std::clamp(value, 0ll, 100ll)) * (rows - 1) + 50) / 100;
			const int x = offset + col;
			if (previous < 0) point(x, row, series);
			else {
				// Rasterize a thin straight segment at dot resolution instead of
				// an entire vertical character column at every change in value.
				int px = x - 1, py = previous;
				const int dy = std::abs(row - previous), step = row >= previous ? 1 : -1;
				int error = 1 - dy;
				while (true) {
					point(px, py, series);
					if (px == x and py == row) break;
					const int twice_error = 2 * error;
					if (twice_error >= -dy) { error -= dy; ++px; }
					if (twice_error <= 1) { error += 1; py += step; }
				}
			}
			previous = row;
		}
	}
	return result;
}
// Keep a stable scale at least as large as the driver power limit. Visible
// peaks can extend it in 50 W steps. Missing readings never become zeros.
inline long long power_scale(const std::deque<Sample>& samples, int visible, long long limit) {
	long long peak = std::max(0ll, limit);
	const size_t first = samples.size() - std::min(samples.size(), static_cast<size_t>(std::max(0, visible)));
	for (size_t i = first; i < samples.size(); ++i) peak = std::max(peak, samples[i].milliwatts);
	return std::max(50000ll, ((peak + 49999) / 50000) * 50000);
}
inline int process_rows(int height, int statistics_height, bool enabled) {
	// Preserve the whole statistics box, three legend rows and at least 3 plot rows.
	if (not enabled) return 0;
	return std::clamp(height - std::max(statistics_height + 2, 9), 0, 9);
}
}
