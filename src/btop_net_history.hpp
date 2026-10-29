// Nova network chart: raw byte rates, independent scales and measured time.
#pragma once
#include "btop_gpu_history.hpp"
#include <array>
#include <cmath>
#include <limits>

namespace NetHistory {
struct Sample {
	std::array<long long, 2> rates{-1, -1}; // download/upload bytes per second
	uint64_t timestamp{}; // steady-clock milliseconds
};
// Auto mode includes every visible peak, so a fresh burst is not clipped
// while the collector's rolling autoscale catches up. Fixed limits stay fixed.
inline std::array<long long,2> scales(const std::deque<Sample>& samples, int visible, long long download, long long upload, bool automatic, bool sync) {
	std::array<long long,2> result{download,upload};
	if (not automatic) return result;
	const size_t first = samples.size() - std::min(samples.size(), static_cast<size_t>(std::max(0, visible)));
	for (size_t i = first; i < samples.size(); ++i) for (int direction = 0; direction < 2; ++direction) {
		const auto rate = samples[i].rates[direction];
		const auto headroom = rate < 0 ? 0 : rate > std::numeric_limits<long long>::max() - rate / 4
			? std::numeric_limits<long long>::max() : rate + rate / 4;
		result[direction] = std::max(result[direction], headroom);
	}
	if (sync) result[0] = result[1] = std::max(result[0],result[1]);
	return result;
}
inline std::deque<GpuHistory::Sample> normalize(const std::deque<Sample>& samples, int visible, long long download, long long upload) {
	std::deque<GpuHistory::Sample> result;
	const size_t first = samples.size() - std::min(samples.size(), static_cast<size_t>(std::max(0, visible)));
	for (size_t i = first; i < samples.size(); ++i) {
		GpuHistory::Sample point;
		point.timestamp = samples[i].timestamp;
		for (int direction = 0; direction < 2; ++direction) {
			const auto maximum = direction == 0 ? download : upload;
			if (samples[i].rates[direction] >= 0 and maximum > 0)
				point.values[direction] = std::llround(std::clamp(static_cast<long double>(samples[i].rates[direction]) * 100 / maximum, 0.L, 100.L));
		}
		result.push_back(point);
	}
	return result;
}
inline double duration(const std::deque<GpuHistory::Sample>& samples) {
	return samples.size() > 1 ? (samples.back().timestamp - samples.front().timestamp) / 1000.0 : 0;
}
}
