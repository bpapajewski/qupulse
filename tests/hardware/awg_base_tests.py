from typing import Callable, Collection, Iterable, List, Optional

from qupulse.hardware.awgs.base import BaseAWG, BaseAWGChannel, BaseAWGChannelTuple, BaseAWGFeature, \
    BaseAWGChannelFeature, BaseAWGChannelTupleFeature


########################################################################################################################
# Features
######################################################################################################################## 

class SynchronizeChannelsFeature(BaseAWGFeature):
    def __init__(self, sync_func: Callable[[int], None]):
        """Storing the callable, to call it if needed below"""
        super().__init__()
        self._sync_func = sync_func

    def synchronize_channels(self, group_size: int) -> None:
        """Forwarding call to callable object, which was provided threw __init__"""
        self._sync_func(group_size)


class ChannelTupleNameFeature(BaseAWGChannelTupleFeature):
    def __init__(self, name_get: Callable[[], str]):
        """Storing the callable, to call it if needed below"""
        super().__init__()
        self._get_name = name_get

    def get_name(self) -> str:
        """Forwarding call to callable object, which was provided threw __init__"""
        return self._get_name()


class ChannelOffsetAmplitudeFeature(BaseAWGChannelFeature):
    def __init__(self, offset_get: Callable[[], float], offset_set: Callable[[float], None],
                 amp_get: Callable[[], float], amp_set: Callable[[float], None]):
        """Storing all callables, to call them if needed below"""
        super().__init__()
        self._get_offset = offset_get
        self._set_offset = offset_set
        self._get_amp = amp_get
        self._set_amp = amp_set

    def get_offset(self) -> float:
        """Forwarding call to callable object, which was provided threw __init__"""
        return self._get_offset()

    def set_offset(self, offset: float) -> None:
        """Forwarding call to callable object, which was provided threw __init__"""
        self._set_offset(offset)

    def get_amplitude(self) -> float:
        """Forwarding call to callable object, which was provided threw __init__"""
        return self._get_amp()

    def set_amplitude(self, amplitude: float) -> None:
        """Forwarding call to callable object, which was provided threw __init__"""
        self._set_amp(amplitude)


########################################################################################################################
# Device & Channels
########################################################################################################################

class TestAWG(BaseAWG):
    def __init__(self, name: str):
        super().__init__(name)

        # Add feature to this object (self)
        # During this call, the function of the feature is dynamically added to this object
        self.add_feature(SynchronizeChannelsFeature(self._sync_chans))

        self._channels = [TestAWGChannel(i, self) for i in range(8)]  # 8 channels
        self._channel_tuples: List["TestAWGChannelTuple"] = []

        # Call the feature function, with the feature's signature
        self.synchronize_channels(2)  # default channel synchronization with a group size of 2

    def cleanup(self) -> None:
        """This will be called automatically in __del__"""
        self._channels.clear()
        self._channel_tuples.clear()

    @property
    def channels(self) -> Collection["TestAWGChannel"]:
        return self._channels

    @property
    def channel_tuples(self) -> Collection["TestAWGChannelTuple"]:
        return self._channel_tuples

    def _sync_chans(self, group_size: int) -> None:
        """Implementation of the feature's function"""
        if group_size not in [2, 4, 8]:  # Allowed group sizes
            raise ValueError("Invalid group size for channel synchronization")

        self._channel_tuples.clear()
        tmp_channel_tuples: List[List["TestAWGChannel"]] = [[] for i in range(len(self._channels) // group_size)]

        # Preparing the channel structure
        for i, channel in enumerate(self._channels):
            tmp_channel_tuples[i // group_size].append(channel)

        # Create channel tuples with its belonging channels and refer to their parent tuple
        for i, tmp_channel_tuple in enumerate(tmp_channel_tuples):
            channel_tuple = TestAWGChannelTuple(i, self, tmp_channel_tuple)
            self._channel_tuples.append(channel_tuple)
            for channel in tmp_channel_tuple:
                channel._set_channel_tuple(channel_tuple)


class TestAWGChannelTuple(BaseAWGChannelTuple):
    def __init__(self, idn: int, device: TestAWG, channels: Iterable["TestAWGChannel"]):
        super().__init__(idn)

        # Add feature to this object (self)
        # During this call, the function of the feature is dynamically added to this object
        self.add_feature(ChannelTupleNameFeature(self._get_name))

        self._device = device
        self._channels = tuple(channels)
        self.sample_rate = 12.456  # default value

    @property
    def sample_rate(self) -> float:
        return self._sample_rate

    @sample_rate.setter
    def sample_rate(self, sample_rate: float) -> None:
        self._sample_rate = sample_rate

    @property
    def device(self) -> TestAWG:
        return self._device

    @property
    def channels(self) -> Collection["TestAWGChannel"]:
        return self._channels
    
    # Feature functions
    def _get_name(self) -> str:
        """Implementation of the feature's function"""
        return chr(ord('A') + self.idn)  # 0 -> 'A',  1 -> 'B',  2 -> 'C', ...


class TestAWGChannel(BaseAWGChannel):
    def __init__(self, idn: int, device: TestAWG):
        super().__init__(idn)

        # Add feature to this object (self)
        # During this call, all functions of the feature are dynamically added to this object
        self.add_feature(ChannelOffsetAmplitudeFeature(self._get_offs,
                                                       self._set_offs,
                                                       self._get_ampl,
                                                       self._set_ampl))

        self._device = device
        self._channel_tuple: Optional[TestAWGChannelTuple] = None
        self._offset = 0.0
        self._amplitude = 5.0

    @property
    def device(self) -> TestAWG:
        return self._device

    @property
    def channel_tuple(self) -> Optional[TestAWGChannelTuple]:
        return self._channel_tuple
    
    def _set_channel_tuple(self, channel_tuple: TestAWGChannelTuple) -> None:
        self._channel_tuple = channel_tuple

    def _get_offs(self) -> float:
        """Implementation of the feature's function"""
        return self._offset
    
    def _set_offs(self, offset: float) -> None:
        """Implementation of the feature's function"""
        self._offset = offset

    def _get_ampl(self) -> float:
        """Implementation of the feature's function"""
        return self._amplitude

    def _set_ampl(self, amplitude: float) -> None:
        """Implementation of the feature's function"""
        self._amplitude = amplitude


########################################################################################################################
# Test
########################################################################################################################

def test():
    device_name = "My device"
    device = TestAWG(device_name)

    # Check if the default values were set correctly
    assert device.name == device_name, "Invalid name for device"
    assert len(device.channels) == 8, "Invalid number of channels"
    assert len(device.channel_tuples) == 4, "Invalid default channel tuples for device"

    # Check if each channel is working correctly
    for i, channel in enumerate(device.channels):
        assert channel.idn == i, "Invalid channel id"
        assert channel.get_offset() == 0, f"Invalid default offset for channel {i}"
        assert channel.get_amplitude() == 5.0, f"Invalid default amplitude for channel {i}"

        offs = -0.1 * i
        ampl = 0.5 + 3 * i
        channel.set_offset(offs)
        channel.set_amplitude(ampl)
        assert channel.get_offset() == offs, f"Invalid offset for channel {i}"
        assert channel.get_amplitude() == ampl, f"Invalid amplitude for channel {i}"

    # Check if each channel tuple is working fine
    for group_size in [2, 4, 8]:
        device.synchronize_channels(group_size)

        assert len(device.channel_tuples) == 8 // group_size, "Invalid number of channel tuples"

        # Check if channels and channel tuples are connected right
        for i, channel in enumerate(device.channels):
            assert channel.channel_tuple.idn == i // group_size, f"Invalid channel tuple {channel.channel_tuple.idn} for channel {i}"
            assert channel in channel.channel_tuple.channels, f"Channel {i} not in its parent channel tuple {channel.channel_tuple.idn}"

    # Check if an error is thrown, when trying to process an invalid parameter
    try:
        device.synchronize_channels(3)
        assert True, "Missing error for invalid group size"
    except ValueError:
        pass
    except:
        assert True, "Wrong error for invalid group size"

    # Check if the channel tuples are still the same
    assert len(device.channel_tuples) == 1, "Invalid number of channel tuples"

    print("Test successful :)")


if __name__ == "__main__":
    test()