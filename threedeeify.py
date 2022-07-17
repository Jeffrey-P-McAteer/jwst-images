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
import pickle

# python -m pip install --user opencv-python
import cv2

# python -m pip install --user numpy
import numpy

# python -m pip install --user scikit-image
import skimage
import skimage.measure

# python -m pip install --user imutils
import imutils
import imutils.contours

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

def crop(img_px, x, y, w, h):
  return img_px[y:y+h, x:x+w]

def rgba_make_transparent_where(img_px, alpha_val=128, condition_statement=lambda x, y, pixel: False):
  for y in range(0, len(img_px)):
    for x in range(0, len(img_px[y])):
      if condition_statement(x, y, img_px[y][x]):
        r = 0
        g = 1
        b = 2
        a = 3
        img_px[y][x][a] = alpha_val

  return img_px

def rgba_make_black_transparent(img_px):
  r = 0
  g = 1
  b = 2
  a = 3
  for y in range(0, len(img_px)):
    for x in range(0, len(img_px[y])):
      # Compute brightness
      px_r = img_px[y][x][r]
      px_g = img_px[y][x][g]
      px_b = img_px[y][x][b]

      img_px[y][x][a] = max(0, min(255, int( ((px_r + px_g + px_b) / (3)) * 3.0 ) ))
      
      # Make dark patches agressively more transparent!
      if img_px[y][x][a] < 84:
        img_px[y][x][a] = int( img_px[y][x][a] * 0.75 )
      # if img_px[y][x][a] < 12:
      #   img_px[y][x][a] = 0

      if img_px[y][x][a] > 84:
        img_px[y][x][a] *= 1.5 # 50% brighter

      if img_px[y][x][a] > 250:
        img_px[y][x][a] = 255

  return img_px


def get_xy_wh(image_pixels, transparent_pixel=None, counted_pixel=None):
  if transparent_pixel is None and counted_pixel is None:
    raise Exception('Must set either counted_pixel or transparent_pixel')
  min_x = 9999999
  max_x = 0
  min_y = 9999999
  max_y = 0
  for y in range(0, len(image_pixels)):
    for x in range(0, len(image_pixels[y])):
      if transparent_pixel is not None:
        if not (image_pixels[y][x] == transparent_pixel):
          if x < min_x:
            min_x = x
          if x > max_x:
            max_x = x
          if y < min_y:
            min_y = y
          if y > max_y:
            max_y = y
      
      if counted_pixel is not None:
        if (image_pixels[y][x] == counted_pixel):
          if x < min_x:
            min_x = x
          if x > max_x:
            max_x = x
          if y < min_y:
            min_y = y
          if y > max_y:
            max_y = y


  return min_x, min_y, max_x - min_x, max_y - min_y



def main(args=sys.argv):
  images = dl_imagery()

  image_tag = 'first-deep-field'
  image_nircam_tif = cv2.imread( images.path(image_tag, 'nircam') )
  #image_miri_tif = cv2.imread( images.path(image_tag, 'miri') )

  # Image begins in sRGB color space
  image_nircam_tif = cv2.cvtColor(image_nircam_tif, cv2.COLOR_RGB2RGBA)

  image_nircam_tif = crop(image_nircam_tif, 0, 0, 1024, 1024) # Make image much smaller to facilitate R&D
  if len(image_nircam_tif) <= 1024:
    print('Warning: using cropped image for fast r&d')
  
  # print(f'image_nircam_tif={image_nircam_tif}')
  # print(f'image_miri_tif={image_miri_tif}')

  entire_img_png_bytes = cv2.imencode('.png', image_nircam_tif)[1].tobytes()
  
  # Segment nircam into a list of features with x,y coordinates in pixels
  image_features = [
    # {'.png': bytes(), 'x': 0, 'y': 0, 'w': 12, 'h': 12, },

  ]
  # image_feature_pickle_file = 'out/image_features.cache.bin'
  # os.makedirs(os.path.dirname(image_feature_pickle_file), exist_ok=True)

  # try:
  #   with open(image_feature_pickle_file, 'rb') as fd:
  #     image_features = pickle.load(fd)
  # except:
  #   traceback.print_exc()

  if len(image_features) < 1:

    nircam_grey = cv2.cvtColor(image_nircam_tif, cv2.COLOR_RGBA2GRAY)
    
    blur_px = 5 # must be odd
    nircam_grey_blur = cv2.GaussianBlur(nircam_grey, (blur_px, blur_px), 0)

    thresh_min = 160
    nircam_grey_thresh = cv2.threshold(nircam_grey_blur, thresh_min, 255, cv2.THRESH_BINARY)[1]
    
    # Clean up noise
    nircam_grey_thresh = cv2.erode(nircam_grey_thresh, None, iterations=2)
    nircam_grey_thresh = cv2.dilate(nircam_grey_thresh, None, iterations=4)

    nircam_labels = skimage.measure.label(nircam_grey_thresh, background=0)[0]
    print(f'nircam_labels={nircam_labels}')
    nircam_mask = numpy.zeros(nircam_grey_thresh.shape, dtype="uint8")

    nircam_mask_min_size = 3
    for label in numpy.unique(nircam_labels):
      # if this is the background label, ignore it
      if label == 0:
        continue
      # otherwise, construct the label mask and count the
      # number of pixels 
      labelMask = numpy.zeros(nircam_grey_thresh.shape, dtype="uint8")
      labelMask[nircam_labels == label] = 255
      numPixels = cv2.countNonZero(labelMask)
      # if the number of pixels in the component is sufficiently
      # large, then add it to our mask of "large blobs"
      if numPixels > nircam_mask_min_size:
        nircam_mask = cv2.add(nircam_mask, labelMask)

      # Store just this labelMask as a segment
      x, y, w, h = get_xy_wh(labelMask, counted_pixel=255)
      segment_img_px = crop(image_nircam_tif, x, y, w, h)
      segment_d = {
        '.png': cv2.imencode('.png', segment_img_px)[1].tobytes(),
        'x': x,
        'y': y,
        'w': w,
        'h': h,
      }
      #print(f'segment_d={segment_d}')
      image_features.append(segment_d)
      print(f'Saved segment number {len(image_features)}')

      print(f'x={x} y={x} w={w} h={h}')
      cv2.imshow('img', segment_img_px)
      cv2.waitKey(0)


    print('nircam_grey_blur:')
    cv2.imshow('img', nircam_grey_blur)
    cv2.waitKey(0)
    cv2.imshow('img', nircam_grey_thresh)
    cv2.waitKey(0)
    cv2.imshow('img', nircam_mask)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


    # for segment_n in range(1, num_segments+1):
    #   # Get min/max image dimensions given mask
    #   n_min_x = 99999
    #   n_max_x = 0
    #   n_min_y = 99999
    #   n_max_y = 0
    #   for y in range(0, len(image_slice_mask)):
    #     for x in range(0, len(image_slice_mask[y])):
    #       if image_slice_mask[y][x] == segment_n:
    #         # we are in segment_n
    #         if x < n_min_x:
    #           n_min_x = x
    #         if x > n_max_x:
    #           n_max_x = x
    #         if y < n_min_y:
    #           n_min_y = y
    #         if y > n_max_y:
    #           n_max_y = y
      
    #   if n_min_x == 99999 and n_min_y == 99999:
    #     continue # segment_n does not exist in image

    #   # Slice bounding box for star
    #   segment_img_px = crop(image_nircam_tif, n_min_x, n_min_y, n_max_x - n_min_x, n_max_y - n_min_y)
    #   #segment_img_px = rgba_make_transparent_where(segment_img_px, 128, lambda x, y, px: image_slice_mask[n_min_y+y][n_min_x+x] != segment_n)
    #   segment_img_px = rgba_make_black_transparent(segment_img_px)

    #   segment_d = {
    #     '.png': cv2.imencode('.png', segment_img_px)[1].tobytes(),
    #     'x': n_min_x,
    #     'y': n_min_y,
    #     'w': n_max_x - n_min_x,
    #     'h': n_max_y - n_min_y,
    #   }
    #   #print(f'segment_d={segment_d}')
    #   image_features.append(segment_d)
    #   print(f'Saved segment_n={segment_n}/{num_segments}')

    try:
      with open(image_feature_pickle_file, 'wb') as fd:
        pickle.dump(image_features, fd)
      print(f'Saved sliced images to {image_feature_pickle_file}')
    except:
      traceback.print_exc()

  print(f'have {len(image_features)} image_features')
  
  # Generate aframe html code

  scene_html_s = ""
#   scene_html_s += '''
# <a-entity position="1.01 0 0" rotation="0 0 0" text="value: 1-0-0; color: #fe0e0e; side: double;"></a-entity>
# <a-entity position="0 1.01 0" rotation="0 0 0" text="value: 0-1-0; color: #0efe0e; side: double;"></a-entity>
# <a-entity position="0 0 1.01" rotation="0 0 0" text="value: 0-0-1; color: #0e0efe; side: double;"></a-entity>
#   '''
  #scene_html_s += '''<a-image transparent="true" position="0 3 -31" src="img/all" width="30" height="30"></a-image>'''


  back_begin = -4
  back_end = -12

  for i, feature in enumerate(image_features):
    depth_val = random.randrange(min(back_begin, back_end), max(back_begin, back_end))
    x = feature.get('x', 0)
    y = feature.get('y', 0)
    w = feature.get('w', 0)
    h = feature.get('h', 0)
    # Scale down, Normalize a bit to fit in default view pane
    x -= 24
    y -= 24
    x /= 100.0
    y /= 100.0
    scene_html_s += f'<a-image transparent="true" position="{x} {y} {depth_val}" src="img/{i}" width="{w/10.0}" height="{h/10.0}"></a-image>\n'
    print(f'Added feature {i} at {round(x, 2)},{round(y, 2)} depth={round(depth_val, 2)}')

  # for x in range(-8, 8, 2):
  #   for y in range(-8, 8, 2):
  #     depth_val = random.randrange(-30, -5)
  #     scene_html_s += f'<a-image transparent="true" position="{x} {y} {depth_val}" src="img/test01"></a-image>\n'


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
    nonlocal image_features
    nonlocal entire_img_png_bytes
    star_id = req.match_info.get('star_id', 'none')
    if star_id == 'all':
      return aiohttp.web.Response(body=entire_img_png_bytes, content_type='image/png')
    try:
      star_id_num = int(star_id)
      if star_id_num >= 0 and star_id_num < len(image_features):
        return aiohttp.web.Response(body=image_features[star_id_num]['.png'], content_type='image/png')
    except:
      traceback.print_exc()
    # Default
    return aiohttp.web.Response(body=entire_img_png_bytes, content_type='image/png')

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

