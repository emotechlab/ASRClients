import argparse
import json
import os
import requests
from sys import exit, stderr


def handle_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('--auth-token', type=str, required=True, help='Authorization token get from Emotech LTD')
    parser.add_argument('--file', type=str, required=True, help='Path to the file to be assessed')
    parser.add_argument('--language', type=str, default='auto', help='Specify the language to assess. [Default] auto')
    parser.add_argument('--version', action='store_true', help='Get ASR server version')
    parser.add_argument('--endpoint', type=str, default='https://asr-whisper-large.api.emotechlab.com', help='URL of the Emotech ASR API to use')

    return parser.parse_args()


def get_response(args):
    URL = args.endpoint
    if args.version:
        url = URL + '/version'
        return requests.get(url)
    else:
        path = os.path.expanduser(args.file)
        if not os.path.exists(path):
            raise FileNotFoundError(path)

        files = {
            'audio': open(path, 'rb')
        }

        headers = {
            'Authorization': 'Bearer ' + args.auth_token.strip()
        }

        if args.language == 'auto':
            url = URL + '/assess'
        else:
            url = URL + '/' + args.language + '/assess'
        return requests.post(url, headers=headers, files=files)


def main():
    # System init.
    args = handle_args()

    response = get_response(args)

    if response.status_code == 200:
        json_ = json.loads(response.text)
        print(json.dumps(json_, indent=4))
    elif response.status_code == 413:
        print("File too large", file=stderr)
    else:
        print("Unexpected response, status code:", response.status_code, file=stderr)
        exit(-1)


if __name__ == '__main__':
    try:
        main()
    except FileNotFoundError as e:
        print("Cannot find file:", e, file=stderr)
    except Exception as e:
        print(e, file=stderr)
