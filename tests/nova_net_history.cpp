#include "../src/btop_net_history.hpp"
#include <cassert>
#include <iostream>
#include <limits>
int main() {
	using namespace NetHistory;
	std::deque<Sample> raw{{{250,50},1000},{{750,150},1500},{{-1,0},2750}};
	assert((scales(raw,3,100,100,false,true)==std::array<long long,2>{100,100}));
	assert((scales(raw,3,100,100,true,false)==std::array<long long,2>{937,187}));
	assert((scales(raw,3,100,100,true,true)==std::array<long long,2>{937,937}));
	assert((scales(raw,1,100,100,true,true)==std::array<long long,2>{100,100}));
	const auto points = normalize(raw,3,1000,200);
	assert(points.size()==3 && points[0].values[0]==25 && points[0].values[1]==25);
	assert(points[1].values[0]==75 && points[1].values[1]==75);
	assert(points[2].values[0]==-1 && points[2].values[1]==0);
	assert(points[0].values[2]==-1 && points[0].values[3]==-1 && points[0].values[4]==-1);
	assert(duration(points)==1.75);
	assert(normalize(raw,0,1000,200).empty());
	const auto tail=normalize(raw,2,500,100);
	assert(tail.size()==2 && tail.front().values[0]==100 && tail.front().values[1]==100);
	assert(duration(tail)==1.25);
	assert(normalize(raw,3,0,-1).front().values[0]==-1);
	raw.push_back({{std::numeric_limits<long long>::max(),1},3000});
	assert(normalize(raw,1,1,1).front().values[0]==100);
	const auto zero=GpuHistory::raster(normalize({{{0,0},0}},1,100,100),4,5);
	assert(zero[4*4+3].series==3);
	std::cout<<"Network raw-rate normalization, independent scales, overflow bounds, missing/zero points, clipping, visible history and measured duration passed\n";
}
