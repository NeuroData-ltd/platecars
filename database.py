#!/usr/bin/env python
from __future__ import absolute_import, division, print_function

import argparse
import collections
import ast
import csv
import os
import requests
import json
import time
from collections import OrderedDict
from pathlib import Path
import streamlit as st
from PIL import Image, ImageFont, ImageDraw, ImageEnhance
import streamlit.components.v1 as stc

import requests
import streamlit as st
import pandas as pd
from webcam import webcam
import datetime
# Security
# passlib,hashlib,bcrypt,scrypt
import hashlib


def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()


def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False


def parse_arguments(args_hook=lambda _: _):
    parser = argparse.ArgumentParser(
        description=
        'Read license plates from images and output the result as JSON or CSV.',
        epilog="""Examples:'
Process images from a folder: python plate_recognition.py -a MY_API_KEY /path/to/vehicle-*.jpg
Use the Snapshot SDK instead of the Cloud Api: python plate_recognition.py -s http://localhost:8080 /path/to/vehicle-*.jpg
Specify Camera ID and/or two Regions: plate_recognition.py -a MY_API_KEY --camera-id Camera1 -r us-ca -r th-37 /path/to/vehicle-*.jpg""",
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-a', '--api-key', help='Your API key.', required=False)
    parser.add_argument(
        '-r',
        '--regions',
        help='Match the license plate pattern of a specific region',
        required=False,
        action="append")
    parser.add_argument(
        '-s',
        '--sdk-url',
        help="Url to self hosted sdk  For example, http://localhost:8080",
        required=False)
    parser.add_argument('--camera-id',
                        help="Name of the source camera.",
                        required=False)
    parser.add_argument('files', nargs='+', help='Path to vehicle images')
    args_hook(parser)
    args = parser.parse_args()
    if not args.sdk_url and not args.api_key:
        raise Exception('api-key is required')
    return args


_session = None


def recognition_api(fp,
                    regions=[],
                    api_key="e2a60c10d2155f1df725c594c5605d6d63a2764c",
                    sdk_url=None,
                    config={},
                    camera_id=None,
                    timestamp=None,
                    mmc=None,
                    exit_on_error=True):
    global _session
    data = dict(regions=regions, config=json.dumps(config))
    if camera_id:
        data['camera_id'] = camera_id
    if mmc:
        data['mmc'] = mmc
    if timestamp:
        data['timestamp'] = timestamp
    response = None
    if sdk_url:
        fp.seek(0)
        response = requests.post(sdk_url + '/v1/plate-reader/',
                                 files=dict(upload=fp),
                                 data=data)
    else:
        if not _session:
            _session = requests.Session()
            _session.headers.update({'Authorization': 'Token ' + api_key})
        for _ in range(3):
            fp.seek(0)
            response = _session.post(
                'https://api.platerecognizer.com/v1/plate-reader/',
                files=dict(upload=fp),
                data=data)
            if response.status_code == 429:  # Max calls per second reached
                time.sleep(1)
            else:
                break

    if response is None:
        return {}
    if response.status_code < 200 or response.status_code > 300:
        print(response.text)
        if exit_on_error:
            exit(1)
    return response.json(object_pairs_hook=OrderedDict)


def flatten_dict(d, parent_key='', sep='_'):
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, collections.MutableMapping):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            if isinstance(v, list):
                items.append((new_key, json.dumps(v)))
            else:
                items.append((new_key, v))
    return dict(items)


def flatten(result):
    plates = result['results']
    del result['results']
    del result['usage']
    if not plates:
        return result
    for plate in plates:
        data = result.copy()
        data.update(flatten_dict(plate))
    return data


def save_results(results, args):
    path = Path(args.output_file)
    if not path.parent.exists():
        print('%s does not exist' % path)
        return
    if not results:
        return
    if args.format == 'json':
        with open(path, 'w') as fp:
            json.dump(results, fp)
    elif args.format == 'csv':
        fieldnames = []
        for result in results[:10]:
            candidate = flatten(result.copy()).keys()
            if len(fieldnames) < len(candidate):
                fieldnames = candidate
        with open(path, 'w') as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames)
            writer.writeheader()
            for result in results:
                writer.writerow(flatten(result))


def custom_args(parser):
    parser.epilog += """
Specify additional engine configuration: plate_recognition.py -a MY_API_KEY --engine-config \'{"region":"strict"}\' /path/to/vehicle-*.jpg
Specify an output file and format for the results: plate_recognition.py -a MY_API_KEY -o data.csv --format csv /path/to/vehicle-*.jpg
Enable Make Model and Color prediction: plate_recognition.py -a MY_API_KEY --mmc /path/to/vehicle-*.jpg"""

    parser.add_argument('--engine-config', help='Engine configuration.')
    parser.add_argument('-o', '--output-file', help='Save result to file.')
    parser.add_argument('--format',
                        help='Format of the result.',
                        default='json',
                        choices='json csv'.split())
    parser.add_argument(
        '--mmc',
        action='store_true',
        help='Predict vehicle make and model. Only available to paying users.')
def main():

    a = st.selectbox("Source de l'image : ", ["Téléverser l'image"])
    if a == "Téléverser l'image":
        img_file_buffer = st.file_uploader("Sélectionnez une image", type=["png", "jpg", "jpeg"])
        if img_file_buffer is not None:
            file_details = {"FileName": img_file_buffer.name, "FileType": img_file_buffer.type}

            with open(os.path.join("./tempDir", "input.png"), "wb") as f:
                f.write(img_file_buffer.getbuffer())
        c = st.columns(10)
        test = c[4].button("Vérification")

        if test:
            paths = ["./tempDir/input.png"]

            results = []
            engine_config = {}

            for path in paths:
                with open(path, 'rb') as fp:
                    api_res = recognition_api(fp, api_key="e2a60c10d2155f1df725c594c5605d6d63a2764c")

                results.append(api_res)
                time_exec = json.dumps(results[0]["processing_time"], indent=2)
                plate_number = json.dumps(results[0]["results"][0]["plate"], indent=2)
                boxes = json.dumps(results[0]["results"][0]["box"], indent=2)
                boxes = ast.literal_eval(boxes)
                c = st.columns(2)
                xmin, ymin, xmax, ymax = boxes["xmin"], boxes["ymin"], boxes["xmax"], boxes["ymax"]
                source_img = Image.open("./tempDir/input.png").convert("RGBA")
                # font_type = ImageFont.truetype("Arial.ttf", 18)
                draw = ImageDraw.Draw(source_img)
                draw.rectangle(((xmin, ymin), (xmax, ymax)), outline=(0, 255, 0), width=3)
                draw.text((xmin - 5, ymin - 10), "Matricule", fill=(0, 255, 0))

                source_img.save("./tempDir/input.png", "PNG")
                im = Image.open("tempDir/input.png")
                im = im.resize((300, 400))
                c[0].image(im)

                plate_number = plate_number.replace('"', "")
                c[1].subheader("Numéro De Matricule:")
                c[1].text(plate_number.upper())


if __name__ == '__main__':
    main()