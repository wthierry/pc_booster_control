#include <booster/robot/channel/channel_subscriber.hpp>
#include <booster/idl/b1/BatteryState.h>

#include <atomic>
#include <chrono>
#include <iostream>
#include <thread>

using namespace booster::robot;
using namespace booster::common;
using namespace booster_interface::msg;

static std::atomic<bool> got(false);
static std::atomic<float> soc_value(0.0f);

void Handler(const void *msg) {
    const auto *bat = static_cast<const BatteryState *>(msg);
    soc_value.store(bat->soc());
    got.store(true);
}

int main() {
    ChannelFactory::Instance()->Init(0);
    ChannelSubscriber<BatteryState> sub("rt/battery_state", Handler);
    sub.InitChannel();

    for (int i = 0; i < 100; ++i) {
        if (got.load()) {
            std::cout << soc_value.load() << std::endl;
            return 0;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    return 2;
}
