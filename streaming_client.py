# System libraries.
import argparse
import base64
import uuid
import json
import time
import threading
import struct
from datetime import datetime
from sys import stderr

# Third party libraries
import numpy as np
import pyaudio
from scipy.io import wavfile
import websocket
from websocket import WebSocketApp

talking = False
t0 = 0.0
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
    parser.add_argument('--auth-token', type=str, required=True, help='Your Emotech authorization token, include it for every request')
    parser.add_argument('--channels', type=int, choices=[1, 2], default=1, help='Number of channels to send to the server')
    parser.add_argument('--rtf-threshold', type=float, default=0.3, help='Threshold to cancel a Whisper inference task. [DEFAULT] 0.3')
    parser.add_argument('--silence-threshold', type=int, default=600, help='Required silence duration in ms after a speech before auto termination. [DEFAULT] 600')
    parser.add_argument('--partial-interval', type=int, default=500, help='Partial transcription will be generated every x ms. [DEFAULT] 500')

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
    frames_per_buffer = 80
    stream = audio.open(format=audio_format, channels=channels, rate=sample_rate, input=True, frames_per_buffer=frames_per_buffer)

    rms_threshold = 4
    audio_buffer = []
    try:
        print(str(datetime.now()), "Recording...")
        while not finish_event.is_set():
            data = stream.read(frames_per_buffer)
            rms = struct.unpack("%sf" % (len(data) // 4), data)
            rms_val = sum([abs(x) for x in rms[0:frames_per_buffer]])
            if rms_val > rms_threshold*2 and not talking:
                print(str(datetime.now()), 'Started talking')
                talking = True
            if rms_val < rms_threshold and talking and t0 == 0.0:
                t0 = time.time()
                print(str(datetime.now()), 'Stopped talking')
            #print(rms_val)
            audio_buffer.append(data)
            if base64:
                ws.send_text(asr_audio_message(data))
            else:
                ws.send_bytes(data)
    except KeyboardInterrupt:
        print("Finished recording.")
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

        stream.stop_stream()
        stream.close()
        audio.terminate()


def on_message(ws, message):
    global t0
    try:
        rsp = json.loads(message)
        print(json.dumps(rsp, indent=4))
        # if rsp['confidence'][0] is not None and float(rsp.get('confidence', [0])[0]) > 0.5:
            # print(f"{datetime.now()} {rsp['transcript'][0]} is_candidate = {rsp['is_candidate']}")
            # print(datetime.now(), json.dumps(rsp, indent=4))

        if not rsp.get('is_partial', True):
            print(f"{datetime.now()} Stream terminated! Response time: {time.time() - t0:.3f}s")
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


def main() -> None:
    args = handle_args()
    global request_id
    request_id = args.request_id if args.request_id != '' else str(uuid.uuid4())


    headers = {
        'Authorization': 'Bearer ' + args.auth_token,
    }

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
        header=headers,
    )
    receive_thread = threading.Thread(target=ws.run_forever)
    receive_thread.start()

    send_thread = threading.Thread(target=record_and_send, args=(ws, args.sample_rate, args.encoding, args.base64, request_id, finish_event, args.channels))
    send_thread.start()


    receive_thread.join()
    finish_event.set()
    ws.close()


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