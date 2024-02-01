# ASR Clients
This repo contains two python clients for Emotech ASR service: Streaming client and non streaming client.
If you just need to run inference on some `wav` files, then it's recommended to use the non-streaming client for best accuracy.
However, if you need to capture your microphone input and do inference on it, then streaming client might be your choice.


# Streaming Client Documentation
## Command Line Arguments

You can run `python3 main.py --help` to see available command line arguments. Some of them have default option.
```text
usage: streaming_client.py [-h] (--file FILE | --microphone) [--request-id REQUEST_ID] [--vad-segment-duration {0.01,0.02,0.03}] [--bit-depth BIT_DEPTH] [--sample-rate SAMPLE_RATE]
                           [--encoding {s16le,s32le,f32le,f64le}] [--max-interval MAX_INTERVAL] [--language LANGUAGE] [--base64] [--keep-connection] --auth-token AUTH_TOKEN

optional arguments:
  -h, --help            show this help message and exit
  --file FILE           Path to audio file for assess
  --microphone          Capture audio from computer microphone
  --request-id REQUEST_ID
                        Request id. [DEFAULT] empty
  --vad-segment-duration {0.01,0.02,0.03}
                        Duration for each VAD segment, [DEFAULT] 0.01
  --bit-depth BIT_DEPTH
                        Audio sample bit depth. [DEFAULT] 32
  --sample-rate SAMPLE_RATE
                        Audio sample rate. [DEFAULT 16000]
  --encoding {s16le,s32le,f32le,f64le}
                        Audio sample encoding. [DEFAULT] f32le
  --max-interval MAX_INTERVAL
                        Max inference interval. WS will return some inference result at least every max_interval seconds. [DEFAULT] 9.0
  --language LANGUAGE   Inference language, [Default] auto
  --base64              Whether to transfer base64 encoded audio or just a binary stream
  --keep-connection     Whether to keep ws connected after inference finished
  --auth-token AUTH_TOKEN
                        Your Emotech authorization token, include it for every request
```

### `--file` and `--microphone`
Only one should be provided to specify input source.

### `--encoding` and `--bit-depth`
They must match, i.e., if you pass `--encoding=s16le --bit-depth=32`, it will be considered invalid.

### `--base64`
Toggle this on to transfer `base64` encoded audio data.

### `--keep-connection`
Toggle this on to prevent server from closing your websocket communication after inference finished.

### `--auth-token`
The token you get from Emotech, It's used to validate who you are.

## How To Use
The client uses three open-source library as dependencies:
- [ffmpeg_python](https://pypi.org/project/ffmpeg-python/), Apache.
- [pyaudio](https://pypi.org/project/PyAudio/), MIT license.
- [websockets](https://pypi.org/project/websockets/), BSD license.


You can install them via `pip3 install -r requirements.txt`

### Troubleshooting
`pyaudio` might failed with a single `pip` command as it relies on other libraries. Here is a detailed instruction on fixing it:

On MacOS:
```shell
# Install brew, skip if you have it already.
mkdir homebrew && curl -L https://github.com/Homebrew/brew/tarball/master | tar xz --strip 1 -C homebrew

brew install portaudio
pip3 install pyaudio
```

On Linux:
```shell
sudo apt-get install libasound-dev portaudio19-dev libportaudio2 libportaudiocpp0
sudo apt-get install ffmpeg libav-tools
pipe install pyaudio
```

On Windows:
```shell
pip install pipwin
pipwin install pyaudio
```

## Example
Send a file to server for inference:
```shell
python3 main.py --file=<PATH/TO/FILE> --auth-token=<YOUR_TOKEN> --language=en
```

Capture microphone audio:
```shell
python3 main.py --microphone --auth-token=<YOUR_TOKEN>
```
NB: This will capture audio from your microphone until it's stopped, you can stop it by pressing `Ctrl + C`.


# Non Streaming Client
## Command Line Arguments
You can run `python3 non_streaming_client.py --help` to see available command line arguments. Some of them have default option.
```text
usage: non_streaming_client.py [-h] --auth-token AUTH_TOKEN --file FILE [--language LANGUAGE] [--version]

optional arguments:
  -h, --help            show this help message and exit
  --auth-token AUTH_TOKEN
                        Authorization token get from Emotech LTD
  --file FILE           Path to the file to be assessed
  --language LANGUAGE   Specity the language to assess. [Default] auto
  --version             Get ASR server version
```

Example:
```shell
python3 non_streaming_client.py --file=<PATH/TO/FILE> --auth-token=<YOUR_TOKEN> --language=en
```


## Test Environment
The clients are tested in MacOS, Ubuntu, Windows.

The clients are tested in Python 3.9, Python 3.11.