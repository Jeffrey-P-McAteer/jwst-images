#!/usr/bin/env python

import os
import sys
import subprocess
import traceback
import time
import shutil
import urllib.request
import socket
import ssl
import random

# python -m pip install --user opencv-python
import cv2

# python -m pip install --user numpy
import numpy

# python -m pip install --user aiohttp
import aiohttp.web


class ImgList(list):
  def path(self, *nicknames):
    for i in self:
      all_nicknames_match = True
      for nickname in nicknames:
        if not nickname in i:
          all_nicknames_match = False
      if all_nicknames_match:
        return i
    return None

def dl_imagery(target_dir='out'):
  os.makedirs(target_dir, exist_ok=True)
  # See https://webbtelescope.org/resource-gallery/images?itemsPerPage=100&Type=Observations&keyword=&=

  images_to_dl = [
    ('https://stsci-opo.org/STScI-01G7DDBNAV8SHNRTMT9AHGC5MF.tif', 'first-deep-field-nircam.tif'),
    ('https://stsci-opo.org/STScI-01G7WE6PKJJ1ZXYKM04SPGMZYD.tif', 'first-deep-field-miri.tif'),
  ]

  all_images = ImgList()
  for img_url, filename in images_to_dl:
    target_file = os.path.join(target_dir, filename)
    all_images.append(os.path.abspath(target_file))
    if os.path.exists(target_file) and os.path.getsize(target_file) > 0:
      print(f'Exists: {target_file}')
      continue
    print(f'Downloading {img_url} to {target_file}')
    urllib.request.urlretrieve(img_url, target_file)

  return all_images


def get_ssl_cert_and_key_or_generate():
  ssl_dir = 'ssl'
  if not os.path.exists(ssl_dir):
    os.makedirs(ssl_dir)
  
  key_file = os.path.join(ssl_dir, 'server.key')
  cert_file = os.path.join(ssl_dir, 'server.crt')

  if os.path.exists(key_file) and os.path.exists(cert_file):
    return cert_file, key_file
  else:
    if os.path.exists(key_file):
      os.remove(key_file)
    if os.path.exists(cert_file):
      os.remove(cert_file)
  
  if not shutil.which('openssl'):
    raise Exception('Cannot find the tool "openssl", please install this so we can generate ssl certificates for our servers! Alternatively, manually create the files {} and {}.'.format(cert_file, key_file))

  generate_cmd = ['openssl', 'req', '-x509', '-sha256', '-nodes', '-days', '28', '-newkey', 'rsa:2048', '-keyout', key_file, '-out', cert_file]
  subprocess.run(generate_cmd, check=True)

  return cert_file, key_file


def get_local_ip():
    """Try to determine the local IP address of the machine."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Use Google Public DNS server to determine own IP
        sock.connect(('8.8.8.8', 80))

        return sock.getsockname()[0]
    except socket.error:
        try:
            return socket.gethostbyname(socket.gethostname())
        except socket.gaierror:
            return '127.0.0.1'
    finally:
        sock.close() 


def main(args=sys.argv):
  images = dl_imagery()

  image_tag = 'first-deep-field'
  image_nircam_tif = cv2.imread( images.path(image_tag, 'nircam') )
  image_miri_tif = cv2.imread( images.path(image_tag, 'miri') )
  
  # print(f'image_nircam_tif={image_nircam_tif}')
  # print(f'image_miri_tif={image_miri_tif}')
  
  # Segment nircam into a list of features with x,y coordinates in pixels

  segment_x = 10
  segment_y = 10
  segment_w = 120
  segment_h = 120
  dumb_segment = image_nircam_tif[segment_y:segment_y+segment_h, segment_x:segment_x+segment_w]
  
  # Zero rgb values close to zero


  # Convert to png bytes
  dumb_segment_png = cv2.imencode('.png', dumb_segment)[1].tobytes()

  
  # Generate aframe html code

  scene_html_s = ""
  scene_html_s += '''
<a-entity position="1.01 0 0" rotation="0 0 0" text="value: 1-0-0; color: #fe0e0e; side: double;"></a-entity>
<a-entity position="0 1.01 0" rotation="0 0 0" text="value: 0-1-0; color: #0efe0e; side: double;"></a-entity>
<a-entity position="0 0 1.01" rotation="0 0 0" text="value: 0-0-1; color: #0e0efe; side: double;"></a-entity>
  '''
  for x in range(-8, 8, 2):
    for y in range(-8, 8, 2):
      depth_val = random.randrange(-30, -5)
      scene_html_s += f'<a-image transparent="true" position="{x} {y} {depth_val}" src="img/test01"></a-image>\n'


  index_html_s = """<!DOCTYPE html>
<html>
  <head>
    <title>"""+image_tag+""" Projection Viewer</title>
    <script src="https://aframe.io/releases/1.3.0/aframe.min.js"></script>
  </head>
  <body>
    <a-scene background="color: #000000">
      """+scene_html_s+"""
    </a-scene>
  </body>
</html>
"""


  # Host aframe html code
  http_port = 4430
  cert_file, key_file = get_ssl_cert_and_key_or_generate()
  server = aiohttp.web.Application()

  async def http_index_req_handler(req):
    nonlocal index_html_s
    return aiohttp.web.Response(text=index_html_s, content_type='text/html')

  async def http_image_req_handler(req):
    nonlocal dumb_segment_png
    star_id = req.match_info.get('star_id', 'none')
    # TODO lookup by star_id
    return aiohttp.web.Response(body=dumb_segment_png, content_type='image/png')

  server.add_routes([
    aiohttp.web.get('/', http_index_req_handler),
    aiohttp.web.get('/index.html', http_index_req_handler),
    aiohttp.web.get('/img/{star_id}', http_image_req_handler),
  ])

  ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
  ssl_ctx.load_cert_chain(cert_file, key_file)
  
  print()
  print(f'Listening on https://0.0.0.0:{http_port}/')
  print(f'LAN address is https://{get_local_ip()}:{http_port}/')
  print()
  aiohttp.web.run_app(server, ssl_context=ssl_ctx, port=http_port)






if __name__ == '__main__':
  main()

