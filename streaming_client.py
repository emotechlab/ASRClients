# System libraries.
import argparse
import asyncio
import base64
import uuid
import json
from sys import stderr

# Third party libraries
import numpy as np
import pyaudio
from scipy.io import wavfile
import websockets
from websockets.exceptions import ConnectionClosedOK


def handle_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('--request-id', type=str, default='', help='Request id. [DEFAULT] empty')
    parser.add_argument('--sample-rate', type=int, default=16000, help='Audio sample rate. [DEFAULT 16000]')
    parser.add_argument('--encoding', type=str, choices=['s16', 's32', 'f32', 'f64'], default='f32', help='Audio sample encoding. [DEFAULT] f32')
    parser.add_argument('--language', type=str, default='auto', help='Inference language, [Default] auto')
    parser.add_argument('--base64', action='store_true', help='Whether to transfer base64 encoded audio or just a binary stream')
    parser.add_argument('--keep-connection', action='store_true', help='Whether to keep ws connected after inference finished')
    parser.add_argument('--auth-token', type=str, required=True, help='Your Emotech authorization token, include it for every request')

    return parser.parse_args()


def asr_start_message(request_id: str, sample_rate: int, encoding: str, keep_connection: bool) -> str:
    start_message = {
        'request':'start',
        'params':{
            'encoding':encoding,
            'sample_rate':sample_rate
        },
        'config':{
            'keep_connection': keep_connection
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


async def record_and_send(ws, sample_rate: int, encoding: str, base64: bool, request_id: str, finish_event: asyncio.Event) -> None:
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
    stream = audio.open(format=audio_format, channels=1, rate=sample_rate, input=True, frames_per_buffer=frames_per_buffer)

    audio_buffer = []
    try:
        print("Recording...")
        while not finish_event.is_set():
            data = stream.read(frames_per_buffer)
            audio_buffer.append(data)
            if base64:
                await ws.send(asr_audio_message(data))
            else:
                await ws.send(data)
                # print("Data sent,", datetime.now())

            # Yield control to allow other tasks to run.
            await asyncio.sleep(0)
    except KeyboardInterrupt:
        print("Finished recording.")
    finally:
        # Save audio.
        filename = './' + request_id + '.wav'
        wavfile.write(filename, sample_rate, np.frombuffer(b''.join(audio_buffer), dtype=np.float32))
        print("audio file write to", filename)

        stream.stop_stream()
        stream.close()
        audio.terminate()
        stop_message = asr_stop_message()
        await ws.send(stop_message)


async def receive_responses(ws, finish_event: asyncio.Event):
    async for message in ws:
        json_ = json.loads(message)
        print(json.dumps(json_, indent=4))
    finish_event.set()
    # Let send task handle audio saving.
    await asyncio.sleep(1)


async def main() -> None:
    args = handle_args()
    request_id = args.request_id if args.request_id != '' else str(uuid.uuid4())

    start_message = asr_start_message(request_id, args.sample_rate, args.encoding, args.keep_connection)

    finish_event = asyncio.Event()

    headers = {
        'Authorization': 'Bearer ' + args.auth_token,
    }

    if args.language == 'auto':
        url = 'ws://goliath.emotechlab.com:5555/ws/assess'
    else:
        url = 'ws://goliath.emotechlab.com:5555/ws/' + args.language + '/assess'

    async with websockets.connect(url, extra_headers=headers) as ws:
        await ws.send(start_message)
        receive_task = receive_responses(ws, finish_event)
        send_task = record_and_send(ws, args.sample_rate, args.encoding, args.base64, request_id, finish_event)

        # Run both tasks concurrently
        await asyncio.gather(send_task, receive_task)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except ConnectionClosedOK:
        pass
    except Exception as e:
        print(e, file=stderr)
