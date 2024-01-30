# StreamingASR
A Python client for streaming ASR service.


# Client Documentation
## Command Line Arguments

You can run `python3 main.py --help` to see available command line arguments. Some of them have default options.
```text
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
                        Max inference interval. WS will return some inference result at least every max_interval seconds. [DEFAULT]
                        9.0
  --ws-url WS_URL       Websocket URL, in the format ws://<IP>:<PORT>/<PATH>
  --base64              Whether to transfer base64 encoded audio or just a binary stream
  --keep-connection     Whether to keep ws connected after inference finished
  --auth-token AUTH_TOKEN
                        Your Emotech authorization token, include it for every requests
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

### If Dependency Installation Failed
`pyaudio` might failed with a single pip command as it relies on other libraries. Here is a detailed instruction on fixing it:

On MaxOS:
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

On Windows: (UNTESTED, [reference](https://stackoverflow.com/questions/52283840/i-cant-install-pyaudio-on-windows-how-to-solve-error-microsoft-visual-c-14))
```shell
pip install pipwin
pipwin install pyaudio
```

## Example
Send a file to server for inference:
```shell
python3 main.py --ws-url=ws://<IP>:<PORT>/<PATH> --file=<PATH/TO/FILE> --auth-token=<YOUR_TOKEN>
```

Capture microphone audio:
```shell
python3 main.py --ws-url=ws://<IP>:<PORT>/<PATH> --microphone --auth-token=<YOUR_TOKEN>
```

NB: Use `/assess` endpoint for automatic language detection, or specify a language as `$LANG/assess` for `ws-url` path. E.g, `/en/assess`.
