#!/usr/bin/env python3
import os
import sys
import struct
import array
import shutil
import tempfile
import cv2
from argparse import ArgumentParser
from PIL import Image

modes = {'sd': (240,136), 'hd': (320,180)}

def human_duration(t):
    dur = []
    while t and len(dur) < 3:
        dur.append(t % 60)
        t = t//60
    if len(dur) == 1: dur.append(0)
    dur.reverse()
    return ':'.join([str(dur[0])] + ['0' * (2 - len(str(n))) + str(n) for n in dur[1:]])

def greatest_common_denom(a, b):
    while b:
        a, b = b, a % b
    return a

def get_metadata(filepath):
    metadata = {}
    if os.path.isfile(filepath):
        vcap = cv2.VideoCapture(filepath)
        if vcap.isOpened():
            metadata['width'] = int(vcap.get(cv2.CAP_PROP_FRAME_WIDTH))
            metadata['height'] = int(vcap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            metadata['aspect'] = float(metadata['width'] / metadata['height'])
            vcap.set(cv2.CAP_PROP_POS_AVI_RATIO,1)
            fps = vcap.get(cv2.CAP_PROP_FPS)
            frame_count = vcap.get(cv2.CAP_PROP_FRAME_COUNT)
            metadata['duration_ms'] = int(frame_count/fps)*1000
            metadata['duration'] = int(frame_count/fps)
            return (True, metadata)
    return (False, metadata)

def extract_images(metadata, directory, args):
    vcap = cv2.VideoCapture(args.filepath)
    if vcap.isOpened():
        # start at [offset] seconds & go to [duration] seconds
        # via [interval] second `skips', saving an image of the
        # proper size each time
        img_count = 0
        if not args.silent:
            print('extracting images... ', end='', flush=True)
            msg = ''
        while (args.offset + (img_count * args.interval)) * 1000 < metadata['duration_ms']:
            pos = args.offset + (img_count * args.interval)
            vcap.set(cv2.CAP_PROP_POS_MSEC, pos * 1000)
            if not args.silent:
                print('\b' * len(msg) + '\x1B[K', end='')
                if not msg == '[{0}%]'.format(int(100 * pos / metadata['duration'])):
                    msg = '[{0}%]'.format(int(100 * pos / metadata['duration']))
                    print(msg, end='', flush=True)
            img_count += 1
            success,img = vcap.read()
            if success:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(img)
                img = img.resize(modes[args.mode], Image.ANTIALIAS)
                filename = (8 - len(str(img_count))) * '0' + str(img_count) + '.jpg'
                img.save(os.path.join(directory, filename))
            else:
                if not args.silent:
                    print('\r\x1B[Kerror capturing frame {0} (@{1}sec)!'.format(img_count, pos))
                    print('could not finish generating bif file.')
                exit(1)
        if not args.silent:
            print('\b' * len(msg) + '\x1B[K', end='')
            print('done ({0} images)'.format(img_count))

def assemble_bif(output_location, img_directory, args):
    magic_number = [0x89,0x42,0x49,0x46,0x0d,0x0a,0x1a,0x0a]
    version = 0

    if not args.silent:
        print('assembling bif file... ', end='', flush=True)
        msg=''
    images = [image for image in os.listdir('{0}'.format(img_directory)) if os.path.splitext(image)[1] == '.jpg']
    images.sort()

    with open(output_location, 'wb') as f:
        array.array('B', magic_number).tofile(f)
        f.write(struct.pack('<I', version))
        f.write(struct.pack('<I', len(images)))
        f.write(struct.pack('<I', 1000 * args.interval))
        array.array('B', [0x00] * 44).tofile(f)

        total_size = 8 * (len(images) + 1)
        index = 64 + total_size

        for n in range(len(images)):
            if not args.silent:
                print('\b' * len(msg) + '\x1B[K', end='')
                msg = '[{0}%]'.format(int(50 * n / len(images)))
                print(msg, end='', flush=True)

            image = images[n]
            f.write(struct.pack('<I', n))
            f.write(struct.pack('<I', index))
            index += os.stat(os.path.join(img_directory, image)).st_size

        f.write(struct.pack('<I', 0xffffffff))
        f.write(struct.pack('<I', index))

        for n in range(len(images)):
            if not args.silent:
                print('\b' * len(msg) + '\x1B[K', end='')
                msg = '[{0}%]'.format(50 + int(50 * n / len(images)))
                print(msg, end='', flush=True)

            data = open(os.path.join(img_directory, images[n]), 'rb').read()
            f.write(data)

        if not args.silent:
            print('\b' * len(msg) + '\x1B[K', end='')
            print('done')

parser = ArgumentParser(description='''generate bif files in order to enable/support
                        positional trickplay thumbnails on roku devices.''')
parser.add_argument('filepath', metavar='sourcevid', type=str, help='video file to process')
parser.add_argument('-i', '--interval', metavar='N', dest='interval', type=int, default=10,
                    help='interval between images in seconds (10 by default)')
parser.add_argument('-O', '--offset', metavar='N', dest='offset', type=int, default=0,
                    help='offset to first image in seconds (0 by default)')
parser.add_argument('-o', '--out', metavar='FILE', dest='output', type=str,
                    help='destination path/file where result will be saved')
parser.add_argument('--sd', dest='mode', action='store_const', const='sd', default='hd',
                    help='resulting bif file will be sd instead of hd')
parser.add_argument('-s', '--silent', dest='silent', action='store_const', const=True, default=False,
                    help='do not print progress or diagnostic information to stdout')

args = parser.parse_args()

success, metadata = get_metadata(args.filepath)
if not success:
    print('error: invalid or corrupt video file')
    exit(1)

gcd=greatest_common_denom(metadata['width'], metadata['height'])
if not args.silent: print('source: {0} (aspect ratio {1}:{2}, runtime {3})'.format(os.path.basename(args.filepath),
                                                                                   int(metadata['width'] / gcd),
                                                                                   int(metadata['height'] / gcd),
                                                                                   human_duration(metadata['duration'])))
width, height = modes[args.mode]
width = int(metadata['aspect'] * height)
modes[args.mode] = (width, height)

temp_dest = tempfile.mkdtemp()
extract_images(metadata, temp_dest, args)
destination = args.output if args.output is not None else \
    '{0}-{1}.bif'.format(os.path.splitext(os.path.basename(args.filepath))[0], args.mode.upper())
assemble_bif(destination, temp_dest, args)
shutil.rmtree(temp_dest)
if not args.silent: print('result: ' + destination)

# vim:fdm=marker
