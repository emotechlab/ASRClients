# System libraries.
import argparse
import base64
import uuid
import json
import os
import threading
import time
from datetime import datetime
from sys import stderr

# Third party libraries
import ffmpeg
import numpy as np
import pyaudio

from scipy.io import wavfile
import websocket
from websocket import WebSocketApp

finish_event = threading.Event()
request_id = ''


def handle_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('--request-id', type=str, default='', help='Request id. [DEFAULT] empty')
    parser.add_argument('--sample-rate', type=int, default=16000, help='Audio sample rate. [DEFAULT 16000]')
    parser.add_argument('--encoding', type=str, choices=['s16', 's32', 'f32', 'f64'], default='f32', help='Audio sample encoding. [DEFAULT] f32')
    parser.add_argument('--language', type=str, default='auto', help='Inference language, [Default] auto')
    parser.add_argument('--base64', action='store_true', help='Whether to transfer base64 encoded audio or just a binary stream')
    parser.add_argument('--single-utterance', action='store_true', help='Whether to keep ws connected after inference finished')
    parser.add_argument('--channels', type=int, choices=[1, 2], default=1, help='Number of channels to send to the server')
    parser.add_argument('--rtf-threshold', type=float, default=0.3, help='Threshold to cancel a Whisper inference task. [DEFAULT] 0.3')
    parser.add_argument('--silence-threshold', type=int, default=600, help='Required silence duration in ms after a speech before auto termination. [DEFAULT] 600')
    parser.add_argument('--partial-interval', type=int, default=500, help='Partial transcription will be generated every x ms. [DEFAULT] 500')
    parser.add_argument('--file', type=str, default='', help='Use existing audio file instead of microphone data')
    parser.add_argument('--snsd', type=str, default='', help='Use with --file option to provide a snsd result.')
    return parser.parse_args()


def asr_start_message(request_id: str, sample_rate: int, encoding: str, single_utterance: bool, channels: int, rtf_thresh: float, silence_thresh: int, partial_interval: int) -> str:
    start_message = {
        'request':'start',
        'params':{
            'encoding': encoding,
            'sample_rate': sample_rate,
            'channel_count': channels,
        },
        'config':{
            'single_utterance': single_utterance,
            'rtf_threshold': rtf_thresh,
            'silence_threshold': silence_thresh,
            'partial_interval': partial_interval,
            'non_partial_interval': 3000
        },
        'channel_index':None
    }
    
    if request_id != '':
        start_message['request_id'] = request_id
    return json.dumps(start_message)


def asr_audio_message(data: bytes) -> str:
    base64_data = base64.b64encode(data).decode('utf-8')
    audio_message = {
        'request': 'audio',
        'data': base64_data,
    }
    return json.dumps(audio_message)


def asr_stop_message() -> str:
    stop_message = {
        'request': 'stop',
        }
    return json.dumps(stop_message)


def record_and_send(ws, sample_rate: int, encoding: str, base64: bool, request_id: str, finish_event: threading.Event, channels: int) -> None:
    global talking
    global t0
    if encoding == 's16':
        audio_format = pyaudio.paInt16
    elif encoding == 's32':
        audio_format = pyaudio.paInt32
    elif encoding == 'f32':
        audio_format = pyaudio.paFloat32
    else:
        # pyaudio does not support float 64.
        print("Microphone does not support f64 audio, using f32 instead", file=stderr)
        encoding = 'f32'
        audio_format = pyaudio.paFloat32

    audio = pyaudio.PyAudio()
    frames_per_buffer = 1600
    stream = audio.open(format=audio_format, channels=channels, rate=sample_rate, input=True, frames_per_buffer=frames_per_buffer)

    audio_buffer = []
    try:
        print(str(datetime.now()), "Recording...")
        while not finish_event.is_set():
            data = stream.read(frames_per_buffer)
            audio_buffer.append(data)
            if base64:
                ws.send_text(asr_audio_message(data))
            else:
                ws.send_bytes(data)
    except websocket.WebSocketConnectionClosedException:
        pass
    finally:
        # Save audio.
        filename = './' + request_id + '.wav'
        if encoding == 's16':
            numpy_audio = np.frombuffer(b''.join(audio_buffer), dtype=np.int16)
        elif encoding == 's32':
            numpy_audio = np.frombuffer(b''.join(audio_buffer), dtype=np.int32)
        elif encoding == 'f32':
            numpy_audio = np.frombuffer(b''.join(audio_buffer), dtype=np.float32)
        else:
            # Because pyaudio does not support float 64.
            numpy_audio = np.frombuffer(b''.join(audio_buffer), dtype=np.float32)
        wavfile.write(filename, sample_rate, numpy_audio)
        print("audio file write to", filename)

        finish_event.set()
        stream.stop_stream()
        stream.close()
        audio.terminate()
        ws.close()


def on_message(ws, message):
    global t0
    try:
        rsp = json.loads(message)
        print(json.dumps(rsp, indent=4))
    except Exception as e:
        print(f"Error processing message: {e}", file=stderr)


def on_close(ws, code, reason):
    global finish_event
    finish_event.set()


def on_error(ws, error):
    print(f"{datetime.now()} WebSocket error: {error}", file=stderr)


def on_open(ws):
    args = handle_args()  # Assuming args are accessible; you might need to adjust scope or pass as a global
    start_message = asr_start_message(request_id, args.sample_rate, args.encoding, args.single_utterance, args.channels, args.rtf_threshold, args.silence_threshold, args.partial_interval)
    ws.send(start_message)


def read_and_send(ws, file_path: str, sample_rate: int, encoding: str, base64: bool, request_id: str, finish_event: threading.Event, channels: int) -> None:
    print("Reading %s" % file_path)
    metadata = ffmpeg.probe(file_path)
    # print(metadata)
    acodec = 'pcm_' + encoding + 'le'
    ar = str(sample_rate // 1000) + 'k'
    try:
        bytes, _ = (
            ffmpeg
                .input(file_path)
                .output('-', format=encoding + 'le', acodec=acodec, ar=ar, ac=1)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
        )
        print(type(bytes), len(bytes))

        seconds = 0.1
        chunk_size = int(seconds * sample_rate * int(encoding[1:]) // 8)
        chunks = (bytes[i: i + chunk_size] for i in range(0, len(bytes), chunk_size))

        if base64:
            for chunk in chunks:
                ws.send_text(asr_audio_message(chunk))
                time.sleep(seconds)
        else:
            for chunk in chunks:
                ws.send_bytes(chunk)
                time.sleep(seconds)
        
        ws.send_text(asr_stop_message())
        ws.close()
    except ffmpeg.Error as e:
        print(e, file=stderr)


def main() -> None:
    args = handle_args()
    global request_id
    request_id = args.request_id if args.request_id != '' else str(uuid.uuid4())

    if args.language == 'auto':
        # url = 'wss://asr-whisper-http.api.emotechlab.com/ws/assess'
        url = 'ws://goliath.emotechlab.com:5555/ws/assess'
    else:
        # url = 'wss://asr-whisper-http.api.emotechlab.com/ws/' + args.language + '/assess'
        url = 'ws://goliath.emotechlab.com:5555/ws/' + args.language + '/assess'

    ws = WebSocketApp(
        url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    receive_thread = threading.Thread(target=ws.run_forever)
    receive_thread.start()

    args.file = os.path.abspath(args.file)
    if validate_file_path(args.file):
        send_thread = threading.Thread(target=read_and_send, args=(ws, args.file, args.sample_rate, args.encoding, args.base64, request_id, finish_event, args.channels))
    else:
        send_thread = threading.Thread(target=record_and_send, args=(ws, args.sample_rate, args.encoding, args.base64, request_id, finish_event, args.channels))
    send_thread.start()

    try:
        receive_thread.join()
    except KeyboardInterrupt:
        finish_event.set()
        ws.close()


def validate_file_path(path: str) -> bool:
    """
    Check if a path exists and if it's indeed a file.
    """
    return os.path.exists(path) and os.path.isfile(path)

if __name__ == '__main__':
    try:
        main()
    except OSError as e:
        print(e, file=stderr)
        print("Below is a summary of your input devices:", file=stderr)
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            print(f"{i}. {dev['name']} - Max Input Channels: {dev['maxInputChannels']}", file=stderr)
        p.terminate()
    except Exception as e:
        print(type(e), e, file=stderr)
