# System libraries.
import argparse
import base64
import colorlog
import uuid
import json
import os
import threading
import time
from typing import Dict, List, Tuple
from datetime import datetime
from sys import exit, stderr

# Third party libraries
import ffmpeg
import numpy as np
import pyaudio
from scipy.io import wavfile
import websocket
from websocket import WebSocketApp

# Global variables.
finish_event = threading.Event()
request_id = ""
logger = None


def handle_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--request-id", type=str, default="", help="Request id. [DEFAULT] empty"
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        help="Audio sample rate. [DEFAULT 16000]",
    )
    parser.add_argument(
        "--encoding",
        type=str,
        choices=["s16", "s32", "f32", "f64"],
        default="f32",
        help="Audio sample encoding. [DEFAULT] f32",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="auto",
        help="Inference language, [Default] auto",
    )
    parser.add_argument(
        "--base64",
        action="store_true",
        help="Whether to transfer base64 encoded audio or just a binary stream",
    )
    parser.add_argument(
        "--single-utterance",
        action="store_true",
        help="Whether to keep ws connected after inference finished",
    )
    parser.add_argument(
        "--channels",
        type=int,
        choices=[1, 2],
        default=1,
        help="Number of channels to send to the server",
    )
    parser.add_argument(
        "--rtf-threshold",
        type=float,
        default=0.3,
        help="Threshold to cancel a Whisper inference task. [DEFAULT] 0.3",
    )
    parser.add_argument(
        "--silence-threshold",
        type=int,
        default=600,
        help="Required silence duration in ms after a speech before auto termination. [DEFAULT] 600",
    )
    parser.add_argument(
        "--partial-interval",
        type=int,
        default=500,
        help="Partial transcription will be generated every x ms. [DEFAULT] 500",
    )
    parser.add_argument(
        "--file",
        type=str,
        default="",
        help="Use existing audio file instead of microphone data",
    )
    parser.add_argument(
        "--snsd",
        type=str,
        default="",
        help="Use with --file option to provide a snsd result.",
    )
    return parser.parse_args()


def asr_start_message(args) -> str:
    start_message = {
        "request": "start",
        "params": {
            "encoding": args.encoding,
            "sample_rate": args.sample_rate,
            "channel_count": args.channels,
        },
        "config": {
            "single_utterance": args.single_utterance,
            "rtf_threshold": args.rtf_threshold,
            "silence_threshold": args.silence_threshold,
            "partial_interval": args.partial_interval,
            "non_partial_interval": 3000,
        },
        "channel_index": None,
    }

    if request_id != "":
        start_message["request_id"] = args.request_id
    return json.dumps(start_message)


def asr_audio_message(data: bytes) -> str:
    base64_data = base64.b64encode(data).decode("utf-8")
    audio_message = {
        "request": "audio",
        "data": base64_data,
    }
    return json.dumps(audio_message)


def asr_stop_message() -> str:
    stop_message = {
        "request": "stop",
    }
    return json.dumps(stop_message)


def record_and_send(ws, finish_event: threading.Event, args) -> None:
    if args.encoding == "s16":
        audio_format = pyaudio.paInt16
    elif args.encoding == "s32":
        audio_format = pyaudio.paInt32
    elif args.encoding == "f32":
        audio_format = pyaudio.paFloat32
    else:
        # pyaudio does not support float 64.
        logger.warn("Microphone does not support f64 audio, using f32 instead")
        args.encoding = "f32"
        audio_format = pyaudio.paFloat32

    audio = pyaudio.PyAudio()
    frames_per_buffer = 1600
    stream = audio.open(
        format=audio_format,
        channels=args.channels,
        rate=args.sample_rate,
        input=True,
        frames_per_buffer=frames_per_buffer,
    )

    audio_buffer = []
    try:
        print(str(datetime.now()), "Recording...")
        while not finish_event.is_set():
            data = stream.read(frames_per_buffer)
            audio_buffer.append(data)
            if args.base64:
                ws.send_text(asr_audio_message(data))
            else:
                ws.send_bytes(data)
    except websocket.WebSocketConnectionClosedException:
        pass
    finally:
        # Save audio.
        filename = "./" + args.request_id + ".wav"
        if args.encoding == "s16":
            numpy_audio = np.frombuffer(b"".join(audio_buffer), dtype=np.int16)
        elif args.encoding == "s32":
            numpy_audio = np.frombuffer(b"".join(audio_buffer), dtype=np.int32)
        elif args.encoding == "f32":
            numpy_audio = np.frombuffer(b"".join(audio_buffer), dtype=np.float32)
        else:
            # Because pyaudio does not support float 64.
            numpy_audio = np.frombuffer(b"".join(audio_buffer), dtype=np.float32)
        wavfile.write(filename, args.sample_rate, numpy_audio)
        print("audio file write to", filename)

        finish_event.set()
        stream.stop_stream()
        stream.close()
        audio.terminate()
        ws.close()


def on_message(ws, message):
    try:
        rsp = json.loads(message)
        print(json.dumps(rsp, indent=4))
    except Exception as e:
        logger.error("Error processing message: %s" % e)


def on_close(ws, code, reason):
    global finish_event
    finish_event.set()
    logger.info("Websocket disconnected with code: %s and reason: %s" % (code, reason))


def on_error(ws, error):
    logger.error("Websocket error: %s" % error)


def on_open(ws):
    args = handle_args()  # Assuming args are accessible; you might need to adjust scope or pass as a global
    start_message = asr_start_message(args)
    ws.send(start_message)


def read_snsd_json(snsd_json: str) -> Dict[str, List[Tuple[int, int]]]:
    """
    Read an snsd json file and extract the start and end time of each segment.
    @param snsd_json: Path to snsd json file. If not provided/invalid, then an empty dictionary will be returned.
    @return: A dict of list of tuples. Each tuple contains exactly two integers representing the time of each segment
    start and end time in ms. Dictionary key is channel index.
    """
    snsd_json = os.path.abspath(snsd_json)
    if not validate_file_path(snsd_json):
        return {"0": []}

    ret = dict()
    with open(snsd_json, "r") as file:
        snsd = json.load(file)
        for i, channel in enumerate(snsd["channels"]):
            segments = []
            for segment in channel["segments"]:
                if segment["is_speech"]:
                    segments.append(
                        (
                            int(segment["start_time"] * 1000),
                            int(segment["end_time"] * 1000),
                        )
                    )
            ret[str(i)] = segments

    logger.debug("According to %s, active segments are: %s" % (snsd_json, ret))
    return ret


def read_and_send(ws, finish_event: threading.Event, args) -> None:
    # Only use the first channel for now.
    # Need to clarify this: when the audio and snsd are both stereo, what should we do? As we only send active segments
    # for inference, what if two channels' active segments does not match? Is it possible to create 'interleave' audio
    # stream in this case?
    segments = read_snsd_json(args.snsd)["0"]
    logger.debug("Reading %s" % args.file)
    metadata = ffmpeg.probe(args.file)

    logger.debug("Audio file metadata: %s" % metadata)
    acodec = "pcm_" + args.encoding + "le"
    ar = str(args.sample_rate // 1000) + "k"
    try:
        bytes, _ = (
            ffmpeg.input(args.file)
            .output(
                "-", format=args.encoding + "le", acodec=acodec, ar=ar, ac=1
            )  # , map_channel='0.0.0')
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )

        if len(segments) == 0:
            # audio is a list of tuple. The tuple is: (audio_bytes, start_time_ms, end_time_ms).
            audios = [(bytes, 0, 0)]
        else:
            audios = []
            for segment in segments:
                start_time_ms = segment[0]
                end_time_ms = segment[1]
                idx_start = int(
                    start_time_ms
                    / 1000
                    * args.sample_rate
                    * int(args.encoding[1:])
                    // 8
                )
                idx_end = int(
                    end_time_ms / 1000 * args.sample_rate * int(args.encoding[1:]) // 8
                )
                audios.append((bytes[idx_start:idx_end], start_time_ms, end_time_ms))

        seconds = 0.1
        chunk_size = int(seconds * args.sample_rate * int(args.encoding[1:]) // 8)
        for audio, start_time_ms, end_time_ms in audios:
            logger.info("Processing %sms -> %sms" % (start_time_ms, end_time_ms))
            chunks = (
                audio[i : i + chunk_size] for i in range(0, len(audio), chunk_size)
            )

            if args.base64:
                for chunk in chunks:
                    if finish_event.is_set():
                        break
                    ws.send_text(asr_audio_message(chunk))
                    time.sleep(seconds)
            else:
                for chunk in chunks:
                    if finish_event.is_set():
                        break
                    ws.send_bytes(chunk)
                    time.sleep(seconds)

            if not finish_event.is_set():
                ws.send_text(asr_stop_message())
                time.sleep(1)
                ws.send_text(asr_start_message(args))
        ws.close()
    except ffmpeg.Error as e:
        logger.error(e)


def main() -> None:
    # System init.
    # Log init.
    global logger
    logger = colorlog.getLogger()
    logger.setLevel(colorlog.DEBUG)
    handler = colorlog.StreamHandler()
    formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
        datefmt=None,
        reset=True,
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
        secondary_log_colors={},
        style="%",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Command line argument init.
    args = handle_args()
    global request_id
    request_id = args.request_id if args.request_id != "" else str(uuid.uuid4())
    args.request_id = request_id
    logger.debug(args)

    if args.language == "auto":
        # url = 'wss://asr-whisper-http.api.emotechlab.com/ws/assess'
        url = "ws://goliath.emotechlab.com:5555/ws/assess"
    else:
        # url = 'wss://asr-whisper-http.api.emotechlab.com/ws/' + args.language + '/assess'
        url = "ws://goliath.emotechlab.com:5555/ws/" + args.language + "/assess"

    ws = WebSocketApp(
        url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    receive_thread = threading.Thread(target=ws.run_forever)
    receive_thread.start()

    send_thread = threading.Thread(
        target=record_and_send, args=(ws, finish_event, args)
    )
    args.file = os.path.abspath(args.file) if args.file != "" else ""
    if args.file == "":
        logger.debug("Using microphone as input source as no input file is provided")
    elif validate_file_path(args.file):
        send_thread = threading.Thread(
            target=read_and_send, args=(ws, finish_event, args)
        )
    else:
        logger.critical("Invalid input file: %s" % args.file)
        ws.close()
        exit(-1)
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


if __name__ == "__main__":
    try:
        main()
    except OSError as e:
        logger.error(e)
        print("Below is a summary of your input devices:", file=stderr)
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            print(
                f"{i}. {dev['name']} - Max Input Channels: {dev['maxInputChannels']}",
                file=stderr,
            )
        p.terminate()
    except Exception as e:
        logger.error("%s: %s" % (type(e), e))
