import unittest
import subprocess
import time
import platform
import os

import pytabor
import numpy as np

from qupulse.hardware.awgs.tabor import TaborDevice, TaborException, TaborSegment, TaborChannelTuple, \
    TaborOffsetAmplitude


class TaborSimulatorManager:
    def __init__(self,
                 simulator_executable='WX2184C.exe',
                 simulator_path=os.path.realpath(os.path.dirname(__file__))):
        self.simulator_executable = simulator_executable
        self.simulator_path = simulator_path

        self.started_simulator = False

        self.simulator_process = None
        self.instrument: TaborDevice = None

    def kill_running_simulators(self):
        command = 'Taskkill', '/IM {simulator_executable}'.format(simulator_executable=self.simulator_executable)
        try:
            subprocess.run([command],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError:
            pass

    @property
    def simulator_full_path(self):
        return os.path.join(self.simulator_path, self.simulator_executable)

    def start_simulator(self, try_connecting_to_existing_simulator=True, max_wait_time=30):
        if try_connecting_to_existing_simulator:
            if pytabor.open_session('127.0.0.1') is not None:
                return

        if not os.path.isfile(self.simulator_full_path):
            raise RuntimeError('Cannot locate simulator executable.')

        self.kill_running_simulators()

        self.simulator_process = subprocess.Popen([self.simulator_full_path, '/switch-on', '/gui-in-tray'])

        start = time.time()
        while pytabor.open_session('127.0.0.1') is None:
            if self.simulator_process.returncode:
                raise RuntimeError('Simulator exited with return code {}'.format(self.simulator_process.returncode))
            if time.time() - start > max_wait_time:
                raise RuntimeError('Could not connect to simulator')
            time.sleep(0.1)

    def connect(self) -> TaborDevice:
        self.instrument = TaborDevice("testDevice",
                                      "127.0.0.1",
                                      reset=True,
                                      paranoia_level=2)

        if self.instrument.main_instrument.visa_inst is None:
            raise RuntimeError('Could not connect to simulator')
        return self.instrument

    def disconnect(self):
        for device in self.instrument.all_devices:
            device.close()
        self.instrument = None

    def __del__(self):
        if self.started_simulator and self.simulator_process:
            self.simulator_process.kill()


@unittest.skipIf(platform.system() != 'Windows', "Simulator currently only available on Windows :(")
class TaborSimulatorBasedTest(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # self.instrument = None
        self.instrument: TaborDevice

    @classmethod
    def setUpClass(cls):
        cls.simulator_manager = TaborSimulatorManager('WX2184C.exe', os.path.dirname(__file__))
        try:
            cls.simulator_manager.start_simulator()
        except RuntimeError as err:
            raise unittest.SkipTest(*err.args) from err

    @classmethod
    def tearDownClass(cls):
        del cls.simulator_manager

    def setUp(self):
        self.instrument = self.simulator_manager.connect()

    def tearDown(self):
        self.instrument.reset()
        self.simulator_manager.disconnect()


class TaborAWGRepresentationTests(TaborSimulatorBasedTest):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def test_sample_rate(self):
        # for ch in (1, 2, 3, 4):
        #   self.assertIsInstance(self.instrument.sample_rate(ch), int)
        # for ch_tuple in self.instrument.channel_tuples:
        #    self.assertIsInstance(ch_tuple.sample_rate,int)

        # with self.assertRaises(TaborException):
        #    self.instrument.sample_rate(0)

        self.instrument.send_cmd(':INST:SEL 1')
        self.instrument.send_cmd(':FREQ:RAST 2.3e9')

        # TODO: int or float self.assertEqual(2300000000, self.instrument.channel_tuples[0].sample_rate)

    def test_amplitude(self):
        # for ch in (1, 2, 3, 4):
        #    self.assertIsInstance(self.instrument.amplitude(ch), float)

        for channel in self.instrument.channels:
            self.assertIsInstance(channel[TaborOffsetAmplitude].amplitude, float)

        self.instrument.send_cmd(':INST:SEL 1; :OUTP:COUP DC')
        self.instrument.send_cmd(':VOLT 0.7')

        self.assertAlmostEqual(.7, self.instrument.channels[0][TaborOffsetAmplitude].amplitude)

    def test_select_marker(self):
        with self.assertRaises(IndexError):
            self.instrument.marker_channels[6].select()

        self.instrument.marker_channels[1].select()
        selected = self.instrument.send_query(':SOUR:MARK:SEL?')
        self.assertEqual(selected, '2')

        self.instrument.marker_channels[0].select()
        selected = self.instrument.send_query(':SOUR:MARK:SEL?')
        self.assertEqual(selected, '1')

    def test_select_channel(self):
        with self.assertRaises(IndexError):
            self.instrument.channels[6].select()

        self.instrument.channels[0].select()
        self.assertEqual(self.instrument.send_query(':INST:SEL?'), '1')

        self.instrument.channels[3].select()
        self.assertEqual(self.instrument.send_query(':INST:SEL?'), '4')


class TaborMemoryReadTests(TaborSimulatorBasedTest):
    def setUp(self):
        super().setUp()

        ramp_up = np.linspace(0, 2 ** 14 - 1, num=192, dtype=np.uint16)
        ramp_down = ramp_up[::-1]
        zero = np.ones(192, dtype=np.uint16) * 2 ** 13
        sine = ((np.sin(np.linspace(0, 2 * np.pi, 192 + 64)) + 1) / 2 * (2 ** 14 - 1)).astype(np.uint16)

        self.segments = [TaborSegment(ramp_up, ramp_up, None, None),
                         TaborSegment(ramp_down, zero, None, None),
                         TaborSegment(sine, sine, None, None)]

        self.zero_segment = TaborSegment(zero, zero, None, None)

        # program 1
        self.sequence_tables = [[(10, 0, 0), (10, 1, 0), (10, 0, 0), (10, 1, 0)],
                                [(1, 0, 0), (1, 1, 0), (1, 0, 0), (1, 1, 0)]]
        self.advanced_sequence_table = [(1, 1, 0), (1, 2, 0)]

        # TODO: darf man das so ersetzen
        # self.channel_pair = TaborChannelTuple(self.instrument, (1, 2), 'tabor_unit_test')
        self.channel_pair = self.instrument.channel_tuples[0]

    def arm_program(self, sequencer_tables, advanced_sequencer_table, mode, waveform_to_segment_index):
        class DummyProgram:
            @staticmethod
            def get_sequencer_tables():
                return sequencer_tables

            @staticmethod
            def get_advanced_sequencer_table():
                return advanced_sequencer_table

            markers = (None, None)
            channels = (1, 2)

            waveform_mode = mode

        self.channel_pair._known_programs['dummy_program'] = (waveform_to_segment_index, DummyProgram)
        self.channel_pair.change_armed_program('dummy_program')

    def test_read_waveforms(self):
        self.channel_pair._amend_segments(self.segments)

        #waveforms sind schon nicht gleich zum alten Treiber
        waveforms = self.channel_pair.read_waveforms()

        segments = [TaborSegment.from_binary_segment(waveform)
                    for waveform in waveforms]

        expected = [self.zero_segment, *self.segments]

        for ex, r in zip(expected, segments):
            ex1, ex2 = ex.data_a, ex.data_b
            r1, r2 = r.data_a, r.data_b
            np.testing.assert_equal(ex1, r1)
            np.testing.assert_equal(ex2, r2)

        self.assertEqual(expected, segments)

    def test_read_sequence_tables(self):
        self.channel_pair._amend_segments(self.segments)
        self.arm_program(self.sequence_tables, self.advanced_sequence_table, None, np.asarray([1, 2]))

        sequence_tables = self.channel_pair.read_sequence_tables()

        actual_sequece_tables = [self.channel_pair._idle_sequence_table] + [[(rep, index + 2, jump)
                                                                             for rep, index, jump in table]
                                                                            for table in self.sequence_tables]

        expected = list(tuple(np.asarray(d)
                              for d in zip(*table))
                        for table in actual_sequece_tables)

        np.testing.assert_equal(sequence_tables, expected)

    def test_read_advanced_sequencer_table(self):
        self.channel_pair._amend_segments(self.segments)
        self.arm_program(self.sequence_tables, self.advanced_sequence_table, None, np.asarray([1, 2]))

        actual_advanced_table = [(1, 1, 1)] + [(rep, idx + 1, jmp) for rep, idx, jmp in self.advanced_sequence_table]

        expected = list(np.asarray(d)
                        for d in zip(*actual_advanced_table))

        advanced_table = self.channel_pair.read_advanced_sequencer_table()

        np.testing.assert_equal(advanced_table, expected)


