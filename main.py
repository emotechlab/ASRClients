# System libraries.
import argparse
import asyncio
import base64
import json
from sys import exit, stderr

# Third party libraries
import ffmpeg
import numpy as np
import websockets


def handle_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('--file', type=str, required=True, help='Path to audio file for assess')
    parser.add_argument('--request-id', type=str, default='', help='Request id. [DEFAULT] empty')
    parser.add_argument('--vad-segment-duration', type=float, choices=[0.01, 0.02, 0.03], default=0.01, help='Duration for each VAD segment, [DEFAULT] 0.01')
    parser.add_argument('--bit-depth', type=int, default=32, help='Audio sample bit depth. [DEFAULT] 32')
    parser.add_argument('--sample-rate', type=int, default=16000, help='Audio sample rate. [DEFAULT 16000]')
    parser.add_argument('--encoding', type=str, choices=['s16le', 's32le', 'f32le', 'f64le'], default='f32le', help='Audio sample encoding. [DEFAULT] f32le')
    parser.add_argument('--max-interval', type=float, default=9.0, help='Max inference interval. WS will return some inference result at least every max_interval seconds. [DEFAULT] 9.0')
    parser.add_argument('--ws-url', type=str, required=True, help='Websocket URL, in the format ws://<IP>:<PORT>/<PATH>')
    parser.add_argument('--base64', action='store_true', help='Whether to transfer base64 encoded audio or just a binary stream')
    parser.add_argument('--keep-connection', action='store_true', help='Whether to keep ws connected after inference finished')

    return parser.parse_args()


def read_audio(file_path: str, encoding: str, sample_rate: int) -> bytes:
    acodec = 'pcm_' + encoding
    ar = str(sample_rate // 1000) + 'k'
    try:
        _info = ffmpeg.probe(file_path)
        out, _err = (ffmpeg
                .input(file_path)
                .output('-', format=encoding, acodec=acodec, ac=1, ar=ar)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
        return out
    except Exception as e:
        raise FileNotFoundError(file_path)


def asr_start_message(request_id: str, vad_segment_duration: float, bit_depth: int, sample_rate: int, encoding: str, max_interval: float) -> str:
    start_message = {
        'type': 'asrstart',
        'vad_segment_duration': vad_segment_duration,
        'bit_depth': bit_depth,
        'sample_rate': sample_rate,
        'encoding': encoding,
        'max_interval': max_interval,
    }
    if request_id != '':
        start_message['request_id'] = request_id
    return json.dumps(start_message)


def asr_audio_message(data: bytes) -> str:
    base64_data = base64.b64encode(data).decode('utf-8')
    audio_message = {
        'type': 'asraudio',
        'data': base64_data,
    }
    return json.dumps(audio_message)


def asr_stop_message(keep_connection: bool) -> str:
    stop_message = {
        'type': 'asrstop',
        'keep_connection': keep_connection,
        }
    return json.dumps(stop_message)


async def main() -> None:
    args = handle_args()
    print(args)
    # A quick sanity check.
    assert str(args.bit_depth) == args.encoding[1: 3], "Contradiction in bit depth and encoding: %s does not match %s" % (args.bit_depth, args.encoding)

    try:
        audio = read_audio(args.file, args.encoding, args.sample_rate)
    except FileNotFoundError as e:
        print("Cannot find file:", e, file=stderr)
        exit(-1)

    start_message = asr_start_message(args.request_id, args.vad_segment_duration, args.bit_depth, args.sample_rate, args.encoding, args.max_interval)
    stop_message = asr_stop_message(args.keep_connection)

    # Each chunk should represent 2 sec of audio.
    chunk_size = 2 * args.sample_rate * (args.bit_depth // 8)
    chunks = (audio[i: i + chunk_size] for i in range(0, len(audio), chunk_size))
    async with websockets.connect(args.ws_url, ping_interval=None) as ws:
        await ws.send(start_message)
        if args.base64:
            for chunk in chunks:
                await ws.send(asr_audio_message(chunk))
        else:
            for chunk in chunks:
                await ws.send(chunk)
        await ws.send(stop_message)

        async for response in ws:
            print(response)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        print(e, file=stderr)