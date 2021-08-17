#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

'''Bit-rate control through controlling the quantization step. In this
    module, no control has been implemented. Both channels are
    quantized using the same step.

    This implementation of the BR control supposes that the
    communication link is symmetric, or at least, the quality of the
    audio for both interlocutors should be the same. This last
    supposition responds to the idea (used in some transmission
    protocols such as Bittorrent) that is "Why I should send more data
    than I'm receiving?"

    Moreover, notice that we don't need to send any extra data to
    perform the BR control.
'''

import numpy as np
import math
import threading
import time
import minimal
from compress3_24 import Compression3_24 as Compression
import logging
#FORMAT = "%(module)s: %(message)s"
#logging.basicConfig(format=FORMAT)

minimal.parser.add_argument("-q", "--minimal_quantization_step", type=int, default=128, help="Minimal quantization step")

class BR_Control(Compression):

    def __init__(self):
        if __debug__:
            print("Running BR_Control.__init__")
        super().__init__()
        self.quantization_step = minimal.args.minimal_quantization_step
        print("(minimum) quantization_step =", minimal.args.minimal_quantization_step)
        self.number_of_sent_chunks = 0
        self.number_of_received_chunks = 0
        data_flow_control_thread = threading.Thread(target=self.data_flow_control)
        data_flow_control_thread.daemon = True
        data_flow_control_thread.start()

    def data_flow_control(self):
        while True:
            time.sleep(1)

    def send(self, packed_chunk):
        super().send(packed_chunk)
        self.number_of_sent_chunks += 1

    def receive(self):
        packed_chunk = super().receive()
        self.number_of_received_chunks += 1
        return packed_chunk

    def quantize(self, chunk):
        '''Dead-zone quantizer.'''
        #quantized_chunk = np.round(chunk / self.quantization_step).astype(np.int16)
        #quantized_chunk = (chunk / self.quantization_step).astype(np.int16)
        quantized_chunk = (chunk / self.quantization_step).astype(np.int32)
        return quantized_chunk
    
    def dequantize(self, quantized_chunk):
        '''Deadzone dequantizer.'''
        chunk = quantized_chunk * self.quantization_step
        return chunk

    def pack(self, chunk_number, chunk):
        '''Quantize and pack a chunk.'''
        quantized_chunk = self.quantize(chunk)
        #quantized_chunk = chunk
        packed_chunk = super().pack(chunk_number, quantized_chunk)
        return packed_chunk

    def unpack(self, packed_chunk):
        '''Dequantize and unpack a chunk.'''
        chunk_number, quantized_chunk = super().unpack(packed_chunk)
        chunk = self.dequantize(quantized_chunk)
        #chunk = quantized_chunk
        return chunk_number, chunk

from compress3_24 import Compression3_24__verbose as Compression__verbose

class BR_Control__verbose(BR_Control, Compression__verbose):
    
    def __init__(self):
        if __debug__:
            print("Running BR_Control__verbose.__init__")
        super().__init__()
        self.average_RMSE = np.zeros(self.NUMBER_OF_CHANNELS)
        self.average_SNR = np.zeros(self.NUMBER_OF_CHANNELS)
        self.accumulated_RMSE_per_cycle = np.zeros(self.NUMBER_OF_CHANNELS)
        self.accumulated_SNR_per_cycle = np.zeros(self.NUMBER_OF_CHANNELS)
        self.average_RMSE_per_cycle = np.zeros(self.NUMBER_OF_CHANNELS)
        self.average_SNR_per_cycle = np.zeros(self.NUMBER_OF_CHANNELS)

        self.recorded_chunks_buff = [None] * self.cells_in_buffer
        for i in range(self.cells_in_buffer):
            self.recorded_chunks_buff[i] = self.zero_chunk

    def stats(self):
        string = super().stats()
        string += "{:>4d}".format(self.quantization_step)
        string += " {}".format(['{:5d}'.format(i) for i in np.round(10**4 * self.average_RMSE_per_cycle / self.frames_per_cycle / self.NUMBER_OF_CHANNELS).astype(np.int)])
        string += " {}".format(['{:3d}'.format(i) for i in np.round(self.average_SNR_per_cycle).astype(np.int)])

        return string
        
    def first_line(self):
        string = super().first_line()
        string += "{:>4s}".format('') # self.quantization_step
        string += "{:>19s}".format('10^4 *') # average_RMSE_per_cycle
        string += "{:>15s}".format('') # average_SNR_per_cycle
        return string

    def second_line(self):
        string = super().second_line()
        string += "{:>4s}".format('Q') # self.quantization_step
        string += "{:>19s}".format('RMSE/sample') # average_RMSE_per_cycle
        string += "{:>15s}".format('SNR[dB]') # average_SNR_per_cycle
        return string

    def separator(self):
        string = super().separator()
        string += f"{'='*(4+19+15)}"
        return string

    def averages(self):
        string = super().averages()
        string += 4*' '
        string += " {}".format(['{:5d}'.format(i) for i in np.round(10**4 * self.average_RMSE / self.frames_per_cycle / self.NUMBER_OF_CHANNELS).astype(np.int)])
        string += " {}".format(['{:3d}'.format(i) for i in np.round(self.average_SNR).astype(np.int)])
        return string
        
    def cycle_feedback(self):
        ''' Computes and shows the statistics. '''
        
        self.average_RMSE_per_cycle = self.accumulated_RMSE_per_cycle / self.chunks_per_cycle
        self.average_RMSE = self.moving_average(self.average_RMSE, self.average_RMSE_per_cycle, self.cycle)

        self.average_SNR_per_cycle = self.accumulated_SNR_per_cycle / self.chunks_per_cycle
        self.average_SNR = self.moving_average(self.average_SNR, self.average_SNR_per_cycle, self.cycle)

        super().cycle_feedback()

        self.accumulated_SNR_per_cycle[:] = 0.0
        self.accumulated_RMSE_per_cycle[:] = 0.0

    def compute(self, indata, outdata):
        # Remember that indata contains the recorded chunk and
        # outdata, the played chunk, but this is only true after
        # running this method.
        
        self.recorded_chunks_buff[self.chunk_number % self.cells_in_buffer] = indata.copy()
        recorded_chunk = self.recorded_chunks_buff[(self.chunk_number - self.chunks_to_buffer - 1) % (self.cells_in_buffer)].astype(np.double)
        played_chunk = outdata.astype(np.double)

        if minimal.args.show_samples:
            print("\033[32mbr_control: ", end=''); self.show_indata(recorded_chunk.astype(np.int))
            print("\033[m", end='')
            # Remember that
            # buffer.Buffering__verbose._record_io_and_play shows also
            # indata and outdata.
        
            print("\033[32mbr_control: ", end=''); self.show_outdata(played_chunk.astype(np.int))
            print("\033[m", end='')

        square_signal = [None] * self.NUMBER_OF_CHANNELS
        for c in range(self.NUMBER_OF_CHANNELS):
            square_signal[c] = recorded_chunk[:, c] * recorded_chunk[:, c]
        # Notice that numpy uses the symbol "*" for computing the dot
        # product of two arrays "a" and "b", that basically is the
        # projection of one of the vectors ("a") into the other
        # ("b"). However, when both vectors are the same and identical
        # in shape (np.arange(10).reshape(10,1) and
        # np.arange(10).reshape(1,10) are the same vector, but one is
        # a row matrix and the other is a column matrix) and the
        # contents are the same, the resulting vector is the result of
        # computing the power by 2, which is equivalent to compute
        # "a**2". Moreover, numpy provides the element-wise array
        # multiplication "numpy.multiply(a, b)" that when "a" and "b"
        # are equal, generaes the same result. Among all these
        # alternatives, the dot product seems to be the faster one.
       
        signal_energy = [None] * self.NUMBER_OF_CHANNELS
        for c in range(self.NUMBER_OF_CHANNELS):
            signal_energy[c] = np.sum( square_signal[c] )
 
        # Compute distortions
        error_signal = [None] * self.NUMBER_OF_CHANNELS
        for c in range(self.NUMBER_OF_CHANNELS):
            error_signal[c] = recorded_chunk[:, c] - played_chunk[:, c]
            
        square_error_signal = [None] * self.NUMBER_OF_CHANNELS
        for c in range(self.NUMBER_OF_CHANNELS):
            square_error_signal[c] = error_signal[c] * error_signal[c]
            
        error_energy = [None] * self.NUMBER_OF_CHANNELS
        for c in range(self.NUMBER_OF_CHANNELS):
            error_energy[c] = np.sum( square_error_signal[c] )

        RMSE = [None] * self.NUMBER_OF_CHANNELS
        for c in range(self.NUMBER_OF_CHANNELS):
            RMSE[c] = math.sqrt( error_energy[c] )
            self.accumulated_RMSE_per_cycle[c] += RMSE[c]

        SNR = [None] * self.NUMBER_OF_CHANNELS
        for c in range(self.NUMBER_OF_CHANNELS):
            if error_energy[c].any():
                if signal_energy[c].any():
                    SNR[c] = 10.0 * math.log( signal_energy[c] / error_energy[c] )
                    self.accumulated_SNR_per_cycle[c] += SNR[c]

    def _record_io_and_play(self, indata, outdata, frames, time, status):

        super()._record_io_and_play(indata, outdata, frames, time, status)
        self.compute(indata, outdata)

    def _read_io_and_play(self, outdata, frames, time, status):

        chunk = super()._read_io_and_play(outdata, frames, time, status)
        self.compute(chunk, outdata)

    def print_final_averages(self):
        super().print_final_averages()
        print(f"Average RMSE (Root Mean Square Error) per sample = {self.average_RMSE / self.frames_per_cycle / self.NUMBER_OF_CHANNELS}")
        print(f"Average SNR (Signal Noise Ratio) in decibels = {self.average_SNR}")

try:
    import argcomplete  # <tab> completion for argparse.
except ImportError:
    print("Unable to import argcomplete (optional)")

if __name__ == "__main__":
    minimal.parser.description = __doc__
    try:
        argcomplete.autocomplete(minimal.parser)
    except Exception:
        if __debug__:
            print("argcomplete not working :-/")
        else:
            pass
    minimal.args = minimal.parser.parse_args()
    if minimal.args.show_stats or minimal.args.show_samples:
        intercom = BR_Control__verbose()
    else:
        intercom = BR_Control()
    try:
        intercom.run()
    except KeyboardInterrupt:
        minimal.parser.exit("\nInterrupted by user")
